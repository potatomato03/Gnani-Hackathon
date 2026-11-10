# VoiceRX

## DEMO

| | |
|---|---|
| **Try it now** | **[gnani-private-clinic-demo.vercel.app/guest](https://gnani-private-clinic-demo.vercel.app/guest)**: one click opens a read-only doctor's dashboard ("Dr Guest") with sample patients, reports, PDFs and WhatsApp follow-ups. Notes on each screen explain what you're seeing. |
| **Solution pitch (1 page)** | [Read on GitHub](docs/SOLUTION_PITCH.md) · [PDF](output/pdf/SOLUTION_PITCH.pdf) |
| **Team sign-in** | [gnani-private-clinic-demo.vercel.app](https://gnani-private-clinic-demo.vercel.app) (private login, for recording and approving) |

A doctor records or dictates a consultation in Hinglish or another Indian language. VoiceRX drafts a structured outpatient note and prescription for the doctor to review and approve. After approval, the report PDF is delivered to the registered WhatsApp number; a prescription voice note is available on request in the patient's saved language. The agent answers from the approved visit and passes unresolved questions to the doctor.

Built for the Gnani AI Great Indian AI Internship Challenge. Speech runs on Gnani Prisma and Timbre.

**Synthetic data only.** Every patient, doctor, phone number, recording and prescription in this repo is made up. This is a hackathon prototype and is not for clinical use.

## Status

The private hospital workspace supports hospital → onboarded doctor → assigned patients, one shared private demo login, encrypted patient phone registration, consent choices and report-specific WhatsApp menus. The active hospitals start with empty rosters; old seeded organisations are archived. Vercel runs the HTTP app and a separate durable worker. See [private demo setup and deployment](docs/PRIVATE_DEMO.md).

The extraction and report pipeline and doctor dashboard run on `aditya/extraction-report`: two checked model stages, medicine matching and instructions, audio capture, audited corrections, approval and PDF/FHIR export. The follow-up bot from `devansh/whatsapp-nlp-bot` is integrated with the same approved records, clinic sessions and database. Its local patient simulator, check-ins, report uploads and doctor tasks are available in the dashboard. A private real-phone Meta test verified JOIN, language/menu replies, read receipts, and a callback request saved to Supabase task/memory state using a synthetic visit. See [WhatsApp integration](docs/whatsapp-integration.md) for setup, verification and transport limitations, and the [runbook](runbook.md) for evaluation results.

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

Install `services/api/requirements.txt` in a Python 3.12 environment. Gemini is tried first; the configured local Ollama model is the fallback. PDF rendering uses the browser named by `PDF_BROWSER`, else installed Edge, Chrome or Chromium; when one prints nothing, the next is tried.

From this repository root in PowerShell (the existing environment is at `../.venv`):

```powershell
$env:PYTHONPATH = 'services/api'
../.venv/Scripts/python -m pytest services/api/tests tools -q
../.venv/Scripts/python -m voicerx.pipeline.run --source typed --run-id typed-1
../.venv/Scripts/python tools/eval/score_report.py runs/typed-1 --source typed
```

Use `--source whisper` for recorded transcripts, `--provider ollama` for local-only evaluation, or `--cases fam-001-a` for one case. Optional `--workers 3` runs independent families concurrently; visits within each family and calls to the local GPU remain sequential. Artifacts and model caches are under ignored `runs/`; scoring summaries are under `data/eval/results/scores/`. Rerunning a case replaces its outputs, including any previous approvals, so use a new run id to preserve reviewed work.

Review `draft_report.json` and `report.pdf`. `python -m voicerx.resolve --help` lists explicit corrections; each correction records its author and reason and creates a new draft version. `python -m voicerx.approve runs/<run>/<case> --by "Reviewer name"` refuses blocking issues or altered content, then writes the approved PDF and FHIR bundles. FHIR exports are not officially validated; patient-language templates and allergy classes await clinical/language review.

## Docs

- [Runbook](runbook.md): status, decisions and everything done so far
- [Decisions](docs/DECISIONS.md)
- [Evals](docs/EVALS.md)
- [Contributions](docs/CONTRIBUTIONS.md)
- [Data rules and sources](data/README.md)
- [Integrated patient follow-up and local simulator](docs/whatsapp-integration.md)
