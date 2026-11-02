# VoiceRx

Working name. A doctor dictates for 15 to 60 seconds in Hinglish or another Indian language. VoiceRx drafts a structured outpatient note and prescription for the doctor to review and approve. After approval, the patient gets their instructions as a voice note in their own language and can call a browser voice agent. The agent answers only from the approved visit and passes everything else to the doctor.

Built for the Gnani AI Great Indian AI Internship Challenge. Speech runs on Gnani Prisma and Timbre.

**Synthetic data only.** Every patient, doctor, phone number, recording and prescription in this repo is made up. This is a hackathon prototype and is not for clinical use.

## Status

The extraction and report pipeline is implemented on `aditya/extraction-report`: two checked model stages, deterministic medicine matching and instructions, draft PDFs, audited corrections, approval and FHIR export. The patient follow-up agent runs as a demo: a simulated WhatsApp chat (`apps/web`) on a small API (`services/api/voicerx/app.py`). After approval it sends the visit summary and timed check-ins, records the patient's answers, answers medicine questions only from the approved prescription, sends warning signs to urgent care, and gives the doctor a list of what needs attention. It works offline on synthetic patients, with text and buttons only. Voice notes, model-read replies, the real WhatsApp connection and the doctor dashboard are future work. See the [runbook](runbook.md) for evaluation results and limitations.

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

Use `--source whisper` for recorded transcripts, `--provider ollama` for local-only evaluation, or `--cases fam-001-a` for one case. Optional `--workers 3` runs independent families concurrently; visits within each family and calls to the local GPU remain sequential. Artifacts and model caches are under ignored `runs/`; scoring summaries are under `data/eval/results/scores/`. Rerunning a case replaces its outputs, including any previous approvals, so use a new run id to preserve reviewed work.

Review `draft_report.json` and `report.pdf`. `python -m voicerx.resolve --help` lists explicit corrections; each correction records its author and reason and creates a new draft version. `python -m voicerx.approve runs/<run>/<case> --by "Reviewer name"` refuses blocking issues or altered content, then writes the approved PDF and FHIR bundles. FHIR exports are not officially validated; patient-language templates and allergy classes await clinical/language review.

## Follow-up chat demo

Needs Python 3.12+ and Node 20+. From the repository root, start the API:

```bash
PYTHONPATH=services/api .venv/bin/uvicorn voicerx.app:app --port 8000
```

In a second terminal, start the web app and open http://localhost:3000:

```bash
cd apps/web && npm install && npm run dev
```

Pick a visit, press **Advance to next check-in** to move the demo clock, and reply with the buttons or by typing. **Reset demo** clears every conversation. Conversations are saved under the ignored `runs/followup-demo/`. Set `NEXT_PUBLIC_API_URL` if the API runs elsewhere. With both running, `node apps/web/scripts/e2e.mjs` checks the main flows in a browser (needs Playwright). Start the API with `VOICERX_FAKE_SPEECH=1` to check the voice controls offline with a fake speech client.

### Voice notes (Gnani Prisma and Timbre)

Voice is off until the API has a Gnani key: set `GNANI_API_KEY` in `.env` (or as an environment variable) and restart the API. Then:

- **▶ Listen** on a clinic message speaks it with Timbre v3.0. Each exact text is synthesised once and cached in `runs/followup-demo/audio/`, so replays cost nothing.
- **🎤** records a voice note of up to 30 seconds. The browser converts it to a 16 kHz WAV, Prisma v3.0 transcribes it, and the transcript goes through the same rules as a typed message. The recording itself is never saved.
- **🔊** (shown while you type) sends the typed text as a synthetic voice note: Timbre speaks it in a patient voice and Prisma transcribes it, so a demo needs no real person's voice.

Every Gnani call spends credits, so nothing is voiced or transcribed until someone asks.

### Starting follow-up from a real approval

Any `approved_report.json` under `runs/` shows up in the app's visit list. To start the follow-up when the doctor approves:

```bash
PYTHONPATH=services/api .venv/bin/python -m voicerx.approve runs/<run>/<case> --by "Dr Name" --review-date 2026-11-12 --followup
```

`--review-date` records a review date the doctor confirms, so the patient is reminded two days before; it is never read from report text. `--followup` sends the visit summary straight away. A patient whose record has no follow-up consent is refused.

`PYTHONPATH=services/api python tools/eval/followup_questions.py` scores the agent on the case files' patient questions.

## Docs

- [Runbook](runbook.md): status, decisions and everything done so far
- [Follow-up agent research](docs/research/followup-agent.md) and [design](docs/superpowers/specs/2026-11-02-followup-agent-design.md)
- [Decisions](docs/DECISIONS.md)
- [Evals](docs/EVALS.md)
- [Contributions](docs/CONTRIBUTIONS.md)
- [Data rules and sources](data/README.md)
