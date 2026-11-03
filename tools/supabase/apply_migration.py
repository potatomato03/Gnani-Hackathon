"""Apply one SQL migration to the Supabase database in a single transaction.

    python -I tools/supabase/apply_migration.py supabase/migrations/<file>.sql

Reads SUPABASE_DB_URL from the environment or the repo's ignored .env, and never prints it.
"""
import os
import sys
from pathlib import Path

import psycopg

ENV = Path(__file__).resolve().parents[2] / '.env'


def db_url():
    value = os.environ.get('SUPABASE_DB_URL', '').strip()
    if not value and ENV.exists():
        for line in ENV.read_text(encoding='utf-8').splitlines():
            if line.startswith('SUPABASE_DB_URL='):
                value = line.split('=', 1)[1].strip()
    if not value:
        raise SystemExit('SUPABASE_DB_URL is not set (.env)')
    return value


def main(argv=None):
    [path] = argv if argv is not None else sys.argv[1:]
    sql = Path(path).read_text(encoding='utf-8')
    with psycopg.connect(db_url(), connect_timeout=15) as db:   # one transaction, committed on success
        db.execute(sql)
    print(f'applied {Path(path).name}')


if __name__ == '__main__':
    main()
