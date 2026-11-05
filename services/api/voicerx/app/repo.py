"""Reads of the app schema, always scoped to the signed-in organisation."""
from ..contracts.report import ApprovedReport, DraftReport
from .db import all_rows, one


def patient_record(row):
    """An app patient in the shape the engine reads (the seed file's shape)."""
    return {'patient_id': row['id'], 'synthetic': row['synthetic'], 'mrn': row['mrn'], 'name': row['name'],
            'sex': row['sex'], 'birth_year': row['birth_year'], 'phone': row['phone'],
            'language_pref': row['language_pref'], 'allergy_status': row['allergy_status'],
            'allergies': list(row['allergies']), 'consents': list(row['consents'])}


def doctor_record(row, organisation_id):
    return {'doctor_id': row['id'], 'synthetic': row['synthetic'], 'clinic_id': organisation_id, 'name': row['display_name'],
            'role': 'doctor', 'specialty': row['specialty'], 'nmc_reg_no': row['registration_no'] or ''}


def clinic_record(row):
    return {'clinic_id': row['id'], 'synthetic': row['synthetic'], 'name': row['name']}


def patient_summary(row):
    return {'id': row['id'], 'mrn': row['mrn'], 'name': row['name'], 'sex': row['sex'], 'birth_year': row['birth_year'],
            'language_pref': row['language_pref'], 'allergy_status': row['allergy_status'],
            'allergies': list(row['allergies']), 'consents': list(row['consents']), 'synthetic': row['synthetic'],
            'last_visit': row.get('last_visit').isoformat() if row.get('last_visit') else None,
            'open_state': row.get('open_state'), 'open_blocking': row.get('open_blocking')}


def list_patients(conn, organisation_id, query, today_only, today,doctor_id=None):
    pattern = '%' + query.strip().lower() + '%' if query else None
    # open_blocking counts the open visit's blocking issues in its latest report, as patient_detail does; null without one.
    return all_rows(conn, '''
        select p.*, last.visit_date as last_visit, open.state as open_state, open.blocking as open_blocking
        from app.patients p
        left join lateral (select visit_date from app.encounters e where e.patient_id = p.id
                           order by visit_date desc, created_at desc limit 1) last on true
        left join lateral (select e.state,
                                  case when rv.report is not null then
                                    (select count(*)::int from jsonb_array_elements(rv.report->'issues') i
                                     where i->>'severity' = 'block') end as blocking
                           from app.encounters e
                           left join lateral (select report from app.report_versions where encounter_id = e.id
                                              order by version desc, (status = 'approved') desc limit 1) rv on true
                           where e.patient_id = p.id and e.state <> 'approved'
                           order by e.created_at desc limit 1) open on true
        where p.organisation_id = %(org)s
          and (%(doctor)s::text is null or p.assigned_doctor_id=%(doctor)s)
          and (%(pattern)s::text is null or lower(p.name) like %(pattern)s or lower(p.mrn) like %(pattern)s
               or lower(p.id) like %(pattern)s)
          and (not %(today_only)s or exists (select 1 from app.encounters e where e.patient_id = p.id and e.visit_date = %(today)s))
        order by last.visit_date desc nulls last, p.name
        limit 100''', {'org': organisation_id, 'pattern': pattern, 'today_only': today_only, 'today': today,'doctor':doctor_id})


def get_patient(conn, organisation_id, patient_id):
    return one(conn, 'select * from app.patients where id = %s and organisation_id = %s', (patient_id, organisation_id))


def get_encounter(conn, organisation_id, encounter_id, lock=False):
    return one(conn, 'select * from app.encounters where id = %s and organisation_id = %s' + (' for update' if lock else ''),
               (encounter_id, organisation_id))


def encounters_of(conn, patient_id):
    return all_rows(conn, '''
        select e.*, u.display_name as clinician_name,
               (select r.state from app.runs r where r.encounter_id = e.id order by r.created_at desc limit 1) as run_state,
               (select r.id from app.runs r where r.encounter_id = e.id order by r.created_at desc limit 1) as run_id
        from app.encounters e join app.users u on u.id = e.clinician_id
        where e.patient_id = %s order by e.visit_date desc, e.created_at desc''', (patient_id,))


def report_row(conn, encounter_id, version=None, status=None):
    return one(conn, '''select * from app.report_versions where encounter_id = %s
                        and (%s::int is null or version = %s) and (%s::text is null or status = %s)
                        order by version desc, (status = 'approved') desc limit 1''',
               (encounter_id, version, version, status, status))


def parse_report(row):
    return (ApprovedReport if row['status'] == 'approved' else DraftReport).model_validate(row['report'])


def approved_reports(conn, patient_id, before_encounter=None):
    rows = all_rows(conn, '''
        select rv.report from app.report_versions rv join app.encounters e on e.id = rv.encounter_id
        where e.patient_id = %s and rv.status = 'approved' and (%s::text is null or e.id <> %s)
        order by e.visit_date, rv.created_at''', (patient_id, before_encounter, before_encounter))
    return [ApprovedReport.model_validate(r['report']) for r in rows]


def approval_of(conn, encounter_id, version):
    return one(conn, '''select a.*, u.display_name as approver_name from app.approvals a
                        join app.users u on u.id = a.approver_id where a.encounter_id = %s and a.version = %s''',
               (encounter_id, version))


def artifacts_of(conn, encounter_id, version=None):
    return all_rows(conn, '''select id, version, kind, state, file_name, sha256, error, created_at, updated_at
                             from app.artifacts where encounter_id = %s and (%s::int is null or version = %s)
                             order by version desc, kind''', (encounter_id, version, version))
