"""Make medicine suggestions for drafts still in review: visits processed before suggestions existed, or after
the method changed. From services/api:

    python -m voicerx.app.backfill_suggestions             (only visits with none stored)
    python -m voicerx.app.backfill_suggestions --all       (replace every stored set)
"""
import sys

from psycopg.types.json import Jsonb

from ..llm.client import build_client
from ..reference import load_reference
from .config import REPO_ROOT, load_settings
from .db import open_pool, transaction
from .repo import parse_report
from .suggest import suggest


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    settings = load_settings()
    open_pool(settings.database_url)
    reference = load_reference(REPO_ROOT)
    client = build_client(REPO_ROOT / '.env', REPO_ROOT / 'runs/cache', only=settings.llm_provider)
    replace = '--all' in sys.argv[1:]
    with transaction() as conn:
        visits = conn.execute('''
            select e.id, e.organisation_id, e.clinician_id, rv.report, rv.status,
                   coalesce(s.text, r.transcript) as transcript
            from app.encounters e
            join app.report_versions rv on rv.encounter_id = e.id and rv.version = e.current_version and rv.status = 'draft'
            join lateral (select * from app.sources where encounter_id = e.id order by version desc limit 1) s on true
            left join lateral (select * from app.runs where encounter_id = e.id order by created_at desc limit 1) r on true
            where e.state = 'in_review' ''').fetchall()
    for visit in visits:
        draft = parse_report(visit)
        unclear = [m for m in draft.checked.medications if m.match != 'exact']
        with transaction() as conn:
            stored = {r['medication_id'] for r in conn.execute(
                'select medication_id from app.medicine_suggestions where encounter_id = %s', (visit['id'],)).fetchall()}
            for rx in unclear:
                if rx.id in stored and not replace:
                    continue
                items, method = suggest(conn, client, visit['transcript'] or '', rx, draft.checked,
                                        visit['organisation_id'], visit['clinician_id'], reference.products)
                conn.execute('insert into app.medicine_suggestions (encounter_id, medication_id, heard, suggestions, method) '
                             'values (%s, %s, %s, %s, %s) on conflict (encounter_id, medication_id) do update set '
                             'heard = excluded.heard, suggestions = excluded.suggestions, method = excluded.method',
                             (visit['id'], rx.id, rx.spoken_name, Jsonb(items), Jsonb(method)))
                print(f"{visit['id']} {rx.spoken_name!r}: {[i['label'] for i in items[:3]]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
