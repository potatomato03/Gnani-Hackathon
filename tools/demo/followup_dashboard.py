"""Create one synthetic dashboard draft from cached stage fixtures; no model or speech calls.

From the repo root: $env:PYTHONPATH='services/api'; ../.venv/Scripts/python tools/demo/followup_dashboard.py
The doctor still approves it in the dashboard. Re-running preserves an existing approved demo.
"""
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from voicerx.app.clinical import process_typed, reference_for
from voicerx.app.config import REPO_ROOT, load_settings, today_in
from voicerx.app.repo import clinic_record, doctor_record, patient_record
from voicerx.fixture_client import FixtureClient
from voicerx.pipeline.run import load_case_inputs
from voicerx.reference import load_reference


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--meta-test', action='store_true', help='create a separate clean synthetic visit for a phone test')
    parser.add_argument('--next-visit', action='store_true', help='create a second synthetic visit for the verified Meta-test patient')
    args = parser.parse_args()
    if args.next_visit and not args.meta_test:
        parser.error('--next-visit requires --meta-test')
    settings = load_settings()
    patient_id, encounter_id = ('pat-whatsapp-demo', 'enc-whatsapp-demo') if args.meta_test else ('pat-followup-demo', 'enc-followup-demo')
    if args.next_visit:
        encounter_id = 'enc-journey-demo'
    mrn, name = ('WA-DEMO', 'WhatsApp Demo (Synthetic)') if args.meta_test else ('FU-DEMO', 'Asha Followup Demo')
    with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=20) as conn:
        if conn.execute('select id from app.encounters where id=%s', (encounter_id,)).fetchone():
            print('Existing synthetic demo preserved:', encounter_id)
            return
        doctor = conn.execute("select u.*, m.organisation_id from app.users u join app.memberships m on m.user_id=u.id "
                              "where u.synthetic and m.role='doctor' order by u.id limit 1").fetchone()
        clinic = conn.execute('select * from app.organisations where id=%s', (doctor['organisation_id'],)).fetchone()
        conn.execute("insert into app.patients(id,organisation_id,mrn,name,sex,birth_year,language_pref,allergy_status,consents,synthetic) "
                     "values(%s,%s,%s,%s,'female',1998,'hi-IN','nka',%s,true) on conflict(id) do nothing",
                     (patient_id, clinic['id'], mrn, name, ['recording', 'ai_processing', 'followup_whatsapp']))
        patient = conn.execute('select * from app.patients where id=%s', (patient_id,)).fetchone()
        reference = reference_for(load_reference(REPO_ROOT), patient_record(patient),
                                  doctor_record(doctor, clinic['id']), clinic_record(clinic))
        case = next(c for c in load_case_inputs(REPO_ROOT, 'typed') if c.case_id == 'fam-001-a')
        visit_date = today_in(clinic['timezone'])
        steps = []
        draft = process_typed(encounter_id, case.transcript, patient_id, doctor['id'], visit_date,
                              FixtureClient(REPO_ROOT / 'services/api/tests/fixtures/fam-001-a'), reference,
                              frozenset(), lambda *step: steps.append(step))
        if any(i.severity == 'block' for i in draft.issues):
            raise RuntimeError('The fixture produced a blocking draft; inspect before proceeding.')
        conn.execute("insert into app.encounters(id,organisation_id,patient_id,clinician_id,visit_date,state,current_version) "
                     "values(%s,%s,%s,%s,%s,'in_review',1)",
                     (encounter_id, clinic['id'], patient_id, doctor['id'], visit_date))
        conn.execute("insert into app.sources(id,encounter_id,kind,language,text,text_sha256,created_by) "
                     "values(%s,%s,'typed','hi-IN',%s,%s,%s)",
                     ('src-' + encounter_id.removeprefix('enc-'), encounter_id, case.transcript, draft.checked.transcript_sha256, doctor['id']))
        conn.execute("insert into app.report_versions(encounter_id,version,status,report,content_hash,created_by) "
                     "values(%s,1,'draft',%s,%s,%s)",
                     (encounter_id, Jsonb(draft.model_dump(mode='json')), draft.content_hash, doctor['id']))
    print('Synthetic fixture processed through extraction/checks/report/assembly:', encounter_id)
    print('Open http://127.0.0.1:8000/#/encounters/' + encounter_id)


if __name__ == '__main__':
    main()
