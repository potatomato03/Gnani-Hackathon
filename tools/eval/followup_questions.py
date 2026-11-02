"""Score the follow-up agent on the case files' patient questions (agent_questions) for the demo visits.

Each question is sent as the first message of a fresh conversation. Reported: the agent's action against
expected_action, and any forbidden claim found in the reply. Synthetic data; no model is called.
Usage, from the repo root: PYTHONPATH=services/api python tools/eval/followup_questions.py
"""
import sys
import tempfile
from collections import Counter
from pathlib import Path

import yaml

from voicerx.agent.conversation import receive, start
from voicerx.agent.demo import DEMO_VISITS, build_visit
from voicerx.pipeline.run import REPO_ROOT

ACTION = {'answer': 'answered', 'escalate': 'escalated', 'urgent': 'urgent', 'clarify': 'clarified'}


def questions():
    for case_id in DEMO_VISITS:
        family = yaml.safe_load((REPO_ROOT / 'data/eval/cases' / (case_id.rsplit('-', 1)[0] + '.yaml'))
                               .read_text(encoding='utf-8'))
        for q in family.get('agent_questions', []):
            if q.get('variant_id') in (None, case_id):
                yield case_id, q


def score():
    rows = []
    with tempfile.TemporaryDirectory() as out:
        visits = {case_id: build_visit(case_id, Path(out)) for case_id in DEMO_VISITS}
        for case_id, q in questions():
            conv = start(visits[case_id], f'eval-{case_id}-{q["id"]}')
            record = receive(conv, text=q['text'])
            forbidden = [c for c in q.get('forbidden_claims', []) if c.casefold() in record.reply_text.casefold()]
            rows.append((case_id, q['id'], q['expected_action'], record.action,
                         record.action == ACTION[q['expected_action']], forbidden))
    return rows


def main():
    rows = score()
    for case_id, qid, expected, got, ok, forbidden in rows:
        print(f'{"ok  " if ok and not forbidden else "MISS"} {case_id} {qid}: expected {expected}, got {got}'
              + (f', forbidden claims {forbidden}' if forbidden else ''))
    totals, hits = Counter(r[2] for r in rows), Counter(r[2] for r in rows if r[4])
    for expected in sorted(totals):
        print(f'{expected}: {hits[expected]} of {totals[expected]}')
    print(f'all: {sum(hits.values())} of {len(rows)}; forbidden claims in replies: '
          f'{sum(len(r[5]) for r in rows)}')
    return 0 if all(r[4] and not r[5] for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
