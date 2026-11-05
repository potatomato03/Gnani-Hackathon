"""Apply the app schema and load the synthetic clinic, doctors and patients.

    python -m voicerx.app.migrate          (from services/api)

Safe to rerun: tables are created if missing and seed rows are upserted.
"""
import json
import sys
from pathlib import Path

import psycopg

from .config import REPO_ROOT, load_settings

MIGRATIONS = Path(__file__).parent / 'migrations'


def seed(conn):
    data = REPO_ROOT / 'data/seed'
    clinic = json.loads((data / 'clinic.json').read_text(encoding='utf-8'))
    conn.execute('insert into app.organisations (id, name, synthetic) values (%s, %s, %s) '
                 'on conflict (id) do update set name = excluded.name',
                 (clinic['clinic_id'], clinic['name'], clinic.get('synthetic', False)))
    for doctor in json.loads((data / 'doctors.json').read_text(encoding='utf-8')):
        conn.execute('insert into app.users (id, display_name, registration_no, specialty, synthetic) '
                     'values (%s, %s, %s, %s, %s) on conflict (id) do update set display_name = excluded.display_name, '
                     'registration_no = excluded.registration_no, specialty = excluded.specialty',
                     (doctor['doctor_id'], doctor['name'], doctor['nmc_reg_no'], doctor['specialty'], doctor['synthetic']))
        conn.execute('insert into app.memberships (user_id, organisation_id, role) values (%s, %s, %s) '
                     'on conflict do nothing', (doctor['doctor_id'], doctor['clinic_id'], doctor['role']))
    for patient in json.loads((data / 'patients.json').read_text(encoding='utf-8')):
        conn.execute('insert into app.patients (id, organisation_id, mrn, name, sex, birth_year, phone, language_pref, '
                     'allergy_status, allergies, consents, synthetic) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) '
                     'on conflict (id) do nothing',
                     (patient['patient_id'], clinic['clinic_id'], patient['mrn'], patient['name'], patient['sex'],
                      patient['birth_year'], patient['phone'], patient['language_pref'], patient['allergy_status'],
                      patient['allergies'], patient['consents'], patient['synthetic']))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    settings = load_settings()
    with psycopg.connect(settings.database_url, connect_timeout=30) as conn:
        for path in sorted(MIGRATIONS.glob('*.sql')):
            conn.execute(path.read_text(encoding='utf-8'))
            print('applied', path.name)
        if '--seed-demo' in sys.argv:
            seed(conn)
        counts = {t: conn.execute(f'select count(*) from app.{t}').fetchone()[0]
                  for t in ('organisations', 'users', 'memberships', 'patients')}
        print('rows', counts)
    return 0


if __name__ == '__main__':
    sys.exit(main())
