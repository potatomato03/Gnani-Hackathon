# VoiceRx

Working name. A doctor dictates for 15 to 60 seconds in Hinglish or another Indian language. VoiceRx drafts a structured outpatient note and prescription for the doctor to review and approve. After approval, the patient gets their instructions as a voice note in their own language and can call a browser voice agent. The agent answers only from the approved visit and passes everything else to the doctor.

Built for the Gnani AI Great Indian AI Internship Challenge. Speech runs on Gnani Prisma and Timbre.

**Synthetic data only.** Every patient, doctor, phone number, recording and prescription in this repo is made up. This is a hackathon prototype and is not for clinical use.

## Status

The extraction and report pipeline is implemented on `aditya/extraction-report`: two checked model stages, deterministic medicine matching and instructions, draft PDFs, audited corrections, approval and FHIR export. The web screens, speech integration and patient voice agent remain future work. See the [runbook](runbook.md) for evaluation results and limitations.

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

Install `services/api/requirements.txt` in a Python 3.12 environment. Gemini is tried first; the configured local Ollama model is the fallback. PDF rendering uses installed Edge/Chromium, or the browser executable specified by `PDF_BROWSER`.

From this repository root in PowerShell (the existing environment is at `../.venv`):

```powershell
$env:PYTHONPATH = 'services/api'
../.venv/Scripts/python -m pytest services/api/tests tools -q
../.venv/Scripts/python -m voicerx.pipeline.run --source typed --run-id typed-1
../.venv/Scripts/python tools/eval/score_report.py runs/typed-1 --source typed
```

Use `--source whisper` for recorded transcripts, `--provider ollama` for local-only evaluation, or `--cases fam-001-a` for one case. Artifacts and model caches are under ignored `runs/`; scoring summaries are under `data/eval/results/scores/`. Rerunning a case replaces its outputs, including any previous approvals, so use a new run id to preserve reviewed work.

Review `draft_report.json` and `report.pdf`. `python -m voicerx.resolve --help` lists explicit corrections; each correction records its author and reason and creates a new draft version. `python -m voicerx.approve runs/<run>/<case> --by "Reviewer name"` refuses blocking issues or altered content, then writes the approved PDF and FHIR bundles. FHIR exports are not officially validated; patient-language templates and allergy classes await clinical/language review.

## Docs

- [Runbook](runbook.md): status, decisions and everything done so far
- [Decisions](docs/DECISIONS.md)
- [Evals](docs/EVALS.md)
- [Contributions](docs/CONTRIBUTIONS.md)
- [Data rules and sources](data/README.md)
