"""Measure suggestions for misheard medicine names on real recordings (spec 2026-11-03, "Measures").

    python tools/eval/medicine_suggestions.py

Each case names a visit in the app database and the heard words; the expected product is matched by its
label. Reports the right product first, the right product in the top three, and a wrong product ranked
first by the model. "not_listed" cases have no right product in any catalogue: there, a model-ranked
first suggestion counts as wrong. "either" cases are sound-alike traps where the doctor must choose.
Uses the database in .env and Groq, so it costs a few model calls.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / 'services/api'))

from voicerx.app.config import load_settings  # noqa: E402
from voicerx.app.db import open_pool, transaction  # noqa: E402
from voicerx.app.repo import parse_report  # noqa: E402
from voicerx.app.suggest import suggest  # noqa: E402
from voicerx.llm.client import build_client  # noqa: E402
from voicerx.reference import load_reference  # noqa: E402

# (visit, heard words, expected label prefix, kind). The heard words are Prisma's mishearings, which stay
# private until Gnani consents (runbook Q-04), so the cases live outside the repo.
CASES_FILE = REPO_ROOT.parent / 'prisma-medicine-cases.json'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    settings = load_settings()
    open_pool(settings.database_url)
    reference = load_reference(REPO_ROOT)
    client = build_client(REPO_ROOT / '.env', REPO_ROOT / 'runs/cache', only=settings.llm_provider)
    totals = {'first': 0, 'top3': 0, 'wrong_first': 0, 'scored': 0}
    cases = json.loads(CASES_FILE.read_text(encoding='utf-8'))['cases']
    for encounter_id, heard, expected, kind in cases:
        expected = tuple(expected) if isinstance(expected, list) else expected
        with transaction() as conn:
            row = conn.execute("select rv.report, rv.status, r.transcript, s.text, e.organisation_id, e.clinician_id "
                               "from app.encounters e join app.sources s on s.encounter_id = e.id "
                               "join app.runs r on r.encounter_id = e.id "
                               "join app.report_versions rv on rv.encounter_id = e.id and rv.version = 1 and rv.status = 'draft' "
                               'where e.id = %s order by r.created_at desc limit 1', (encounter_id,)).fetchone()
            if row is None:
                print(f'{heard:16} visit {encounter_id} not found; skipped')
                continue
            draft = parse_report(row)
            rx = next((m for m in draft.checked.medications if m.spoken_name == heard), None)
            if rx is None:
                print(f'{heard:16} not among the visit\'s medicines; skipped')
                continue
            items, method = suggest(conn, client, row['transcript'] or row['text'], rx, draft.checked,
                                    row['organisation_id'], reference.products)
        labels = [i['label'] for i in items]
        hits = lambda label: label.startswith(expected) if isinstance(expected, str) else (
            any(label.startswith(e) for e in expected) if expected else False)
        # Only a first suggestion shown as "likely" claims anything; "possible matches" make the doctor pick.
        likely = bool(items) and items[0]['likely']
        if kind == 'one':
            first, top3 = bool(labels) and hits(labels[0]), any(hits(l) for l in labels[:3])
            wrong = likely and not first
        elif kind == 'not_listed':
            first = top3 = not likely
            wrong = likely
        else:
            first = top3 = all(any(l.startswith(e) for l in labels[:3]) for e in expected)
            wrong = False
        totals['scored'] += 1
        totals['first'] += first
        totals['top3'] += top3
        totals['wrong_first'] += wrong
        print(f'{heard:16} {kind:10} first={"yes" if first else "no ":3} top3={"yes" if top3 else "no ":3} '
              f'likely={"yes" if likely else "no ":3} wrong_likely={"YES" if wrong else "no"}')
        for item in items[:3]:
            print(f'    {item["label"][:46]:46} {item["tier"]:9} sound {item["sound"]:.2f} fit {item["fit"]}'
                  f'{" sibling" if item["sound_alike_sibling"] else ""} | {item["reason"] or "(not ranked by the model)"}')
    print(f"\nright product first {totals['first']}/{totals['scored']}, in top three {totals['top3']}/{totals['scored']}, "
          f"a wrong product shown as likely {totals['wrong_first']}/{totals['scored']}")


if __name__ == '__main__':
    main()
