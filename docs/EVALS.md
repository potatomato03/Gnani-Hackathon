# Evals

The extraction and report results are in the [runbook](../runbook.md) under Verification.

## Follow-up agent: patient questions

Build: `claude/vibrant-archimedes-umbogz`, the follow-up demo (rules and buttons, no model). Data: the `agent_questions` of the three demo visits (`fam-001-a`, `fam-004-a`, `fam-010-a`), typed. Each question is the first message of a fresh conversation. Script: `tools/eval/followup_questions.py`.

| Expected action | Result |
|---|---|
| Answer from the approved prescription | 3 of 3 |
| Pass to the doctor | 3 of 3 |
| Urgent | 1 of 1 |
| Forbidden claims in any reply | 0 of 7 replies |

Coverage: 7 of the 29 patient questions in the case files. The other 22 belong to visits that have no saved stage outputs yet, so they can't run offline. These 7 are **development data**: they were visible while the keyword and red-flag rules were written, so they show the rules work as intended, not how they generalise. No held-out questions exist yet.

Report every result as numerator/denominator with coverage, and name the build and data it came from. Synthetic results are not evidence of real-clinic performance.

Prisma accuracy and keyterm comparison results stay out of this repo until Gnani gives written consent. See the open question in [DECISIONS.md](DECISIONS.md).
