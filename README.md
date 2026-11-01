# VoiceRx

Working name. A doctor dictates for 15 to 60 seconds in Hinglish or another Indian language. VoiceRx drafts a structured outpatient note and prescription for the doctor to review and approve. After approval, the patient gets their instructions as a voice note in their own language and can call a browser voice agent. The agent answers only from the approved visit and passes everything else to the doctor.

Built for the Gnani AI Great Indian AI Internship Challenge. Speech runs on Gnani Prisma and Timbre.

**Synthetic data only.** Every patient, doctor, phone number, recording and prescription in this repo is made up. This is a hackathon prototype and is not for clinical use.

## Status

There is no application code yet. The first synthetic cases and their checker are on the `aditya/data-setup` branch. See the [runbook](runbook.md).

## Layout

```
apps/web/                 Next.js: doctor, patient and admin screens
services/api/voicerx/
  contracts/              Pydantic models, the single source of truth
  ingest/                 Gnani realtime, REST and batch adapters
  pipeline/               Evidence ledger, drug matcher, extraction, schedule parsing, rules
  agent/                  Routing, red flags, grounding, planner, gate, language templates
  exports/                PDF and FHIR
  jobs/                   Worker loop over the jobs table
  db/                     Queries scoped by clinic, patient and visit
services/api/tests/       Unit, contract and integration tests
data/                     Synthetic data, see data/README.md
tools/corpus/             Scripts that generate and render the synthetic corpus
supabase/migrations/      Database schema
docs/                     Decisions, eval results, contributions
```

## Setup

Copy `.env.example` to `.env` and fill in your keys. Keys stay on the backend and never go in git.

## Docs

- [Runbook](runbook.md): status, decisions and everything done so far
- [Decisions](docs/DECISIONS.md)
- [Evals](docs/EVALS.md)
- [Contributions](docs/CONTRIBUTIONS.md)
- [Data rules and sources](data/README.md)
