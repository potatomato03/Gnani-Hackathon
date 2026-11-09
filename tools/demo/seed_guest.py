"""Seed the read-only guest clinic that visitors open from the sign-in page or /guest (runbook D-146).

    python tools/demo/seed_guest.py            # build or rebuild the guest clinic
    python tools/demo/seed_guest.py --dry-run  # show what would be copied, write nothing

Copies the finished synthetic visits of the demo hospitals into one made-up clinic with one made-up doctor
(auth.GUEST_ORG, auth.GUEST_USER). Every id gets a new, stable one; every clinic and doctor name becomes the
guest's; report fingerprints are recomputed, and the approved PDFs and FHIR bundles are printed again so they
carry the guest names too. Phone numbers, WhatsApp contacts, join codes, provider message ids and recordings are
not copied, so the worker has nothing to send for these patients and an inbound WhatsApp message can never reach
them. Running it again replaces the guest clinic's records with a fresh copy; the source records are untouched.
"""
from hashlib import sha256
import argparse
from pathlib import Path
import re
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / 'services/api'))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

from voicerx.app.auth import GUEST_ORG, GUEST_USER  # noqa: E402
from voicerx.app.config import read_env  # noqa: E402
from voicerx.app.repo import parse_report  # noqa: E402
from voicerx.app.worker import TEMPLATES  # noqa: E402
from voicerx.exports.fhir import build_bundles  # noqa: E402
from voicerx.exports.patient_box import build_patient_box  # noqa: E402
from voicerx.exports.pdf.render import html_to_pdf, render_html  # noqa: E402
from voicerx.pipeline.assemble import content_hash  # noqa: E402

GUEST_CLINIC = 'ARDAI Guest Clinic'
GUEST_DOCTOR = 'Dr Guest'
# Copied in this order; removed in the reverse order.
TABLES = ('patients', 'encounters', 'sources', 'runs', 'report_versions', 'approvals', 'artifacts',
          'medicine_shortlists', 'medicine_suggestions', 'followups', 'patient_deliveries', 'clinic_report_jobs',
          'patient_memory')
# Deliveries still waiting would be picked up by the worker; only finished ones are copied.
FINISHED = {'accepted': 'delivered', 'sent': 'sent', 'delivered': 'delivered', 'read': 'read', 'failed': 'failed',
            'cancelled': 'cancelled'}


def patient_key(clinic_id, patient_id):
    """The follow-up memory key of a patient (app/followup.py)."""
    return 'app-' + sha256(f'{clinic_id}/{patient_id}'.encode()).hexdigest()[:32]


def new_id(old):
    """The same prefix with a stable new hex tail, so a rebuild keeps the guest URLs."""
    tail = re.search(r'[0-9a-f]{6,}$', old)
    fresh = sha256(f'guest/{old}'.encode()).hexdigest()
    return old[:tail.start()] + fresh[:len(tail.group())] if tail else old + '-guest'


class Rewriter:
    """Replaces ids, names and fingerprints inside every string, list and JSON value of a row."""

    def __init__(self):
        self.map = {}
        self.pattern = None

    def add(self, old, new):
        if old and old != new:
            self.map[old.lower()] = new
            self.pattern = None

    def __call__(self, value):
        if isinstance(value, str):
            if self.pattern is None:
                keys = sorted(self.map, key=len, reverse=True)
                self.pattern = re.compile('|'.join(re.escape(k) for k in keys), re.IGNORECASE) if keys else None
            return self.pattern.sub(lambda m: self.map[m.group(0).lower()], value) if self.pattern else value
        if isinstance(value, list):
            return [self(v) for v in value]
        if isinstance(value, dict):
            return {self(k): self(v) for k, v in value.items()}
        return value


def column_types(conn):
    rows = conn.execute("select table_name, column_name, udt_name from information_schema.columns "
                        "where table_schema = 'app'").fetchall()
    types = {}
    for r in rows:
        types.setdefault(r['table_name'], {})[r['column_name']] = r['udt_name']
    return types


def read_sources(conn):
    orgs = conn.execute('select id, name from app.organisations where synthetic and archived_at is null '
                        'and id <> %s', (GUEST_ORG,)).fetchall()
    org_ids = [o['id'] for o in orgs]
    # Patients with at least one approved visit; visits that got as far as a recording or typed notes.
    patients = conn.execute("""select p.* from app.patients p where p.organisation_id = any(%s) and p.synthetic
        and exists (select 1 from app.encounters e where e.patient_id = p.id and e.state = 'approved')
        order by p.created_at""", (org_ids,)).fetchall()
    pids = [p['id'] for p in patients]
    encounters = conn.execute("""select e.* from app.encounters e where e.patient_id = any(%s)
        and exists (select 1 from app.sources s where s.encounter_id = e.id) order by e.created_at""", (pids,)).fetchall()
    eids = [e['id'] for e in encounters]
    by = lambda sql, keys: conn.execute(sql, (keys,)).fetchall()
    rows = {'patients': patients, 'encounters': encounters,
            'sources': by('select * from app.sources where encounter_id = any(%s)', eids),
            'runs': by('select * from app.runs where encounter_id = any(%s) order by created_at', eids),
            'report_versions': by("select * from app.report_versions where encounter_id = any(%s) "
                                  "order by encounter_id, version, status desc", eids),
            'approvals': by('select * from app.approvals where encounter_id = any(%s)', eids),
            'artifacts': by('select * from app.artifacts where encounter_id = any(%s)', eids),
            'medicine_shortlists': by('select * from app.medicine_shortlists where encounter_id = any(%s)', eids),
            'medicine_suggestions': by('select * from app.medicine_suggestions where encounter_id = any(%s)', eids),
            'followups': by('select * from app.followups where encounter_id = any(%s)', eids)}
    fids = [f['id'] for f in rows['followups']]
    rows['patient_deliveries'] = by('select * from app.patient_deliveries where followup_id = any(%s)', fids)
    rows['clinic_report_jobs'] = by('select * from app.clinic_report_jobs where encounter_id = any(%s) '
                                    'order by created_at', eids)
    keys = [patient_key(p['organisation_id'], p['id']) for p in patients]
    rows['patient_memory'] = by('select * from app.patient_memory where patient_key = any(%s)', keys)
    doctors = conn.execute("select distinct u.id, u.display_name from app.users u join app.memberships m on "
                           "m.user_id = u.id where m.organisation_id = any(%s)", (org_ids,)).fetchall()
    return orgs, doctors, rows


def build_rewriter(orgs, doctors, rows):
    rewrite = Rewriter()
    for org in orgs:
        rewrite.add(org['id'], GUEST_ORG)
        rewrite.add(org['name'], GUEST_CLINIC)
    for doctor in doctors:
        rewrite.add(doctor['id'], GUEST_USER)
    # Clinic and doctor names as they were printed on each report, including names a clinic had before a rename.
    clinic_names = {r['report']['header']['clinic_name'] for r in rows['report_versions']}
    doctor_names = {r['report']['header']['doctor_name'] for r in rows['report_versions']}
    doctor_names |= {d['display_name'] for d in doctors if d['display_name'] != 'Demo administrator'}
    for name in clinic_names:
        rewrite.add(name, GUEST_CLINIC)
    for name in doctor_names:
        for form in (name, 'Dr ' + name, 'Dr. ' + name):
            rewrite.add(form, GUEST_DOCTOR)
    for table in ('patients', 'encounters', 'sources', 'runs', 'approvals', 'artifacts', 'followups',
                  'patient_deliveries', 'clinic_report_jobs'):
        for row in rows[table]:
            rewrite.add(row['id'], new_id(row['id']))
    for p in rows['patients']:
        rewrite.add(patient_key(p['organisation_id'], p['id']), patient_key(GUEST_ORG, new_id(p['id'])))
    return rewrite


def refingerprint(rows, rewrite):
    """Recompute each report's fingerprint in version order: a version's fingerprint covers its predecessor's."""
    for row in rows['report_versions']:
        report = rewrite(row['report'])
        parsed = parse_report({**row, 'report': report})
        fresh = content_hash(parsed)
        rewrite.add(report['content_hash'], fresh)
        row['report'] = {**report, 'content_hash': fresh}
        row['content_hash'] = fresh


def guest_rows(rows, rewrite):
    out = {table: [{k: rewrite(v) for k, v in row.items()} for row in rows[table]] for table in TABLES}
    for p in out['patients']:
        p.update(phone=None, phone_encrypted=None, phone_last4=None)
    for f in out['followups']:
        conversation = dict(f['conversation'])
        conversation['contact'] = None
        f.update(conversation=conversation, join_hash=None, join_expires_at=None)
    for d in out['patient_deliveries']:
        d['provider_id'] = None
    out['patient_deliveries'] = [d for d in out['patient_deliveries'] if d['state'] in FINISHED]
    for d in out['patient_deliveries']:
        d['state'] = FINISHED[d['state']]
    jobs = [j for j in out['clinic_report_jobs'] if j['state'] in FINISHED]
    kept = {j['id'] for j in jobs}
    for j in jobs:
        j.update(state=FINISHED[j['state']], provider_id=None, recipient='guest-' + j['delivery_mode'],
                 source_job=j['source_job'] if j['source_job'] in kept else None)
    # A job that resends another comes after it.
    ordered, placed = [], set()
    while len(ordered) < len(jobs):
        ready = [j for j in jobs if j['id'] not in placed and (j['source_job'] is None or j['source_job'] in placed)]
        ordered += ready
        placed |= {j['id'] for j in ready}
    out['clinic_report_jobs'] = ordered
    return out


def remove_guest(conn):
    encounters = "(select id from app.encounters where organisation_id = %(org)s)"
    followups = "(select id from app.followups where organisation_id = %(org)s)"
    for sql in (f'delete from app.artifact_files where artifact_id in (select id from app.artifacts where encounter_id in {encounters})',
                f'delete from app.report_files where encounter_id in {encounters}',
                'delete from app.clinic_report_jobs where organisation_id = %(org)s',
                f'delete from app.patient_deliveries where followup_id in {followups}',
                'delete from app.followups where organisation_id = %(org)s',
                f'delete from app.medicine_shortlists where encounter_id in {encounters}',
                f'delete from app.medicine_suggestions where encounter_id in {encounters}',
                f'delete from app.artifacts where encounter_id in {encounters}',
                f'delete from app.approvals where encounter_id in {encounters}',
                f'delete from app.report_versions where encounter_id in {encounters}',
                f'delete from app.runs where encounter_id in {encounters}',
                f'delete from app.sources where encounter_id in {encounters}',
                'delete from app.encounters where organisation_id = %(org)s',
                "delete from app.patient_memory where patient_key = any(%(keys)s)",
                'delete from app.patients where organisation_id = %(org)s'):
        keys = [patient_key(GUEST_ORG, r['id']) for r in
                conn.execute('select id from app.patients where organisation_id = %s', (GUEST_ORG,)).fetchall()]
        conn.execute(sql, {'org': GUEST_ORG, 'keys': keys})


def insert(conn, table, row, types):
    cols = list(row)
    values = [Jsonb(row[c]) if types[table][c] == 'jsonb' and row[c] is not None else row[c] for c in cols]
    conn.execute(f'insert into app.{table} ({", ".join(cols)}) values ({", ".join(["%s"] * len(cols))})', values)


def print_files(conn, out):
    """The approved PDF and FHIR bundle of each copied visit, printed again from the guest report."""
    approved = {(r['encounter_id'], r['version']): r for r in out['report_versions'] if r['status'] == 'approved'}
    with tempfile.TemporaryDirectory() as folder:
        for artifact in out['artifacts']:
            row = approved.get((artifact['encounter_id'], artifact['version']))
            if artifact['state'] != 'ready' or row is None:
                continue
            report = parse_report(row)
            if artifact['kind'] == 'report_pdf':
                path = html_to_pdf(render_html(report, build_patient_box(report, TEMPLATES)),
                                   Path(folder) / f"{artifact['id']}.pdf")
                data = path.read_bytes()
            else:
                import json
                data = json.dumps(build_bundles(report), ensure_ascii=False, indent=2).encode('utf-8')
            digest = sha256(data).hexdigest()
            conn.execute('insert into app.artifact_files(artifact_id, sha256, data) values (%s, %s, %s)',
                         (artifact['id'], digest, data))
            if artifact['kind'] == 'report_pdf':
                conn.execute("insert into app.report_files(encounter_id, version, sha256, data, status) "
                             "values (%s, %s, %s, %s, 'approved')",
                             (artifact['encounter_id'], artifact['version'], digest, data))
            conn.execute('update app.artifacts set sha256 = %s where id = %s', (digest, artifact['id']))
            print(f"  printed {artifact['kind']} for {artifact['encounter_id']} v{artifact['version']}")


def leftovers(out, rewrite):
    """Any source clinic or doctor name, or source id, still in the copy."""
    text = repr(out).lower()
    return sorted(old for old in rewrite.map if old in text)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    with psycopg.connect(read_env()['SUPABASE_DB_URL'], row_factory=dict_row, prepare_threshold=None) as conn:
        types = column_types(conn)
        orgs, doctors, rows = read_sources(conn)
        rewrite = build_rewriter(orgs, doctors, rows)
        refingerprint(rows, rewrite)
        out = guest_rows(rows, rewrite)
        for table in TABLES:
            print(f'{table}: {len(out[table])}')
        print('patients:', ', '.join(p['name'] for p in out['patients']))
        left = leftovers(out, rewrite)
        if left:
            print('WARNING: source names still present:', left)
        if args.dry_run:
            conn.rollback()
            return 0
        conn.execute("insert into app.organisations(id, name, timezone, synthetic) values (%s, %s, 'Asia/Kolkata', true) "
                     'on conflict (id) do update set name = excluded.name, archived_at = null', (GUEST_ORG, GUEST_CLINIC))
        conn.execute("insert into app.users(id, display_name, specialty, synthetic) values (%s, %s, 'general_medicine', true) "
                     'on conflict (id) do update set display_name = excluded.display_name, disabled_at = null',
                     (GUEST_USER, GUEST_DOCTOR))
        conn.execute("insert into app.memberships(user_id, organisation_id, role) values (%s, %s, 'doctor') "
                     'on conflict do nothing', (GUEST_USER, GUEST_ORG))
        remove_guest(conn)
        for table in TABLES:
            for row in out[table]:
                insert(conn, table, row, types)
        print_files(conn, out)
        conn.commit()
    print('Guest clinic ready.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
