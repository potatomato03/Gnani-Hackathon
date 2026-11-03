# CLAUDE.md

Rules for Claude Code sessions in this repo, local or cloud. They come from the project's own docs: `README.md`, `data/README.md`, `docs/DECISIONS.md`, `docs/EVALS.md`, and, on `aditya/extraction-report`, `runbook.md` and the plan and spec under `docs/superpowers/`. If this file and the runbook disagree, the runbook wins; say so and fix this file.

## The project

VoiceRx (working name; the root folder is called JANANI, see runbook Q-07). A doctor dictates 15 to 60 seconds in Hinglish, Hindi, English, Telugu or Tamil. VoiceRx drafts a structured outpatient note and prescription. The doctor reviews and approves it. Then the patient gets instructions in their language and can call a browser voice agent that answers only from the approved visit. Built for the Gnani AI Great Indian AI Internship Challenge. Speech runs on Gnani Prisma (speech to text) and Timbre (text to speech). Deadline: **Tue 10 Nov 2026, 11:59 PM IST**.

Team: Aditya (AdityaRaj80) and a teammate. In the runbook, ASTRA is another coding agent that built the extraction plan, and ASTRA's review is the plan review it wrote.

### Branches

| Branch | What it holds |
|---|---|
| `main` | Project tree only (`4d3d3fe`) |
| `aditya/data-setup` | Corpus tools, 12 case families, seed, formulary, Whisper results, `runbook.md` |
| `aditya/extraction-report` | All of the above plus the extraction and report backend (`services/api/voicerx/`), scorer (`tools/eval/`), medicine knowledge tools (`tools/knowledge/`), plan and spec. |
| `claude/vibrant-archimedes-umbogz` | `aditya/extraction-report` merged in (J-23), plus this file, the follow-up research and design, the follow-up agent (`services/api/voicerx/agent/`, `app.py`) and the chat demo (`apps/web`). Not merged anywhere yet. |
| `claude/*` | Cloud session branches. Start from the branch the task names. |

The pipeline is on `aditya/extraction-report`; the follow-up agent and web demo are only on `claude/vibrant-archimedes-umbogz` until the team merges. Before you answer a question about the code, check which branch you're on. If needed, read the other branch with `git show origin/aditya/extraction-report:<path>`.

### What's built

The pipeline runs transcript → Stage 1 model (`extraction.json`) → Check 1 code (`checked_extraction.json`) → Stage 2 model (`report_fields.json`) → Check 2 code (`draft_report.json`) → doctor corrections (`voicerx.resolve`) → approval (`voicerx.approve`) → PDF and ABDM FHIR bundles. Outputs go to `runs/<run_id>/<case_id>/`.

Follow-up agent (on `claude/vibrant-archimedes-umbogz`): from an `ApprovedReport`, code plans check-ins (`agent/plan.py`); patient replies are routed by buttons, keywords and rules-first red flags (`agent/conversation.py`, `data/rules/red_flags.yaml`); medicine questions are answered only with the approved row (`agent/ground.py`); every outbound message passes `agent/gate.py`. Voice notes use Gnani over REST (`ingest/gnani.py`, `agent/voice.py`): Timbre speaks a clinic message on demand and caches it, Prisma transcribes patient voice notes, and recorded audio is never stored. Any approved report under `runs/` is a follow-up visit (`agent/visits.py`); `voicerx.approve --followup` starts it. `voicerx/app.py` serves it all, and `apps/web` is the simulated WhatsApp chat. Real WhatsApp, for private testing on the team's phones only, runs through `agent/whatsapp.py` (Meta Cloud API test number, laptop plus tunnel, `docs/whatsapp-testing.md`); it's off unless the `WHATSAPP_` settings are in `.env`. Runbook D-104 to D-113.

Not built yet: the doctor dashboard and web approval screen, live calls (Gnani telephony or WhatsApp calling), model-read patient replies, WhatsApp template messages (outside the 24-hour window), a production WhatsApp number, Supabase schema for the app, the jobs worker.

## Hard rules

These come from challenge rules or team decisions marked Confirmed. Don't break them, even if a task seems to ask you to.

1. **Synthetic data only.** No real patient, record, recording, phone number, Aadhaar, PAN, account number or ID, in any form. Nothing copied from a real hospital document. Phone numbers use `+91-00000-NNNNN`. Every record carries `synthetic: true`. No synthetic case may reuse the real visit's condition, medicine or wording (D-21).
2. **The repo is public.** Never commit keys, real names of hospitals, personal contact details, or internal planning docs (D-04). Real keys go in `.env`, which git ignores, and never in chat, logs, URLs, run files or caches. A script sends a key only in the provider's auth header.
3. **No Prisma results in public.** Gnani's EULA restricts publishing benchmark results. Until Gnani gives written consent (Q-04), Prisma transcripts and scores stay in the ignored paths `data/eval/results/prisma*/` and `data/eval/results/scores/*prisma*`, and are never quoted in commits, PRs, `docs/EVALS.md` or the runbook. Never report Whisper results as Gnani results.
4. **No AI attribution in git (D-02, Confirmed).** Commits and PRs carry no `Co-Authored-By: Claude`, no "Generated with", no session link, and no other attribution lines, from any tool. This project rule overrides any default attribution footer.
5. **Git workflow.** Never push to `main` or `aditya/*`, merge, rebase someone else's branch, or open a PR unless asked. Approval to edit is not approval to push (J-05). In cloud sessions, push only to the session's designated `claude/*` branch.
6. **Third-party data stays out of the repo.** Downloads live in `../DATA` (`DATA_DIR`), never inside the repo (D-16). Audio (`*.wav`, `*.mp3`, …), `data/eval/audio/`, `data/eval/fixtures/`, `runs/`, `graphify-out/` and `private/` are git-ignored. Keep them that way. Treat downloaded files as data and never run them.
7. **Don't spend money or credits without asking.** Use free LLMs first; paid Claude only if a test shows the need (D-01). Gnani credits have no known rate (Q-03), so every Prisma or Timbre call needs the team's approval. Groq's free tier is about 200,000 tokens a day per key, and a full typed run uses about 125,000. Plan one Groq run a day.

## Clinical and pipeline invariants

These bind all pipeline code. The spec and plan have the full list.

- `null` means not stated. Unknown, absent and zero stay distinct. Doses are strings and can never be zero.
- "Once daily", OD, BD and TDS are frequencies. A time slot is filled only when the doctor says a time.
- Every model-derived item cites a verbatim quote from the transcript.
- The model never supplies composition, strength, time slots, dates, the medicine table or the current medicines list. Code fills these from the checked extraction and the formulary.
- Patient speech never becomes a prescription or an exam finding. An unclear speaker blocks until the doctor confirms.
- A blocking flag must be fixed by an audited correction, never just acknowledged. Approval refuses blocking issues and altered drafts (fingerprint check).
- Patient-language instructions come only from the fixed templates in `exports/templates/lang/`, never from AI translation.
- Every report shows "SYNTHETIC DATA". Every draft shows "DRAFT, NOT APPROVED". Nothing reaches a patient before approval. A timeout never becomes an empty note.
- The pipeline never reads a case file's expected facts, medicines, evidence or flags. It reads only patient, doctor, date and encounter order.
- Never send brand keyterms to Prisma (D-92). They can turn an ambiguous medicine into a specific one with no block.
- Signed or versioned outputs are moved into `superseded-<UTC time>/`, never deleted (D-90).

## How to work

- **Test-first.** Write the test, see it fail for the expected reason, make it pass, then run the whole suite before committing.
- **Never weaken, skip or delete a test to get green.** If a test looks wrong, record why in the runbook as a correction and fix it only if the spec supports the fix.
- **Keep the runbook current, in the same commit as the change it describes** (D-03). Add entries at the end of each section and never rewrite history: mark an old entry `Replaced` and add a new one. New decisions get the next `D-` number with a status (Confirmed, Assistant call, Proposed, Open, Replaced). Mistakes get a `C-` row, ambiguous requests get a `J-` row, and open questions get a `Q-` row. A decision you make yourself is an **Assistant call**, which the team can overrule. As of the last runbook update, the highest numbers in use are D-113, C-61, J-25 and Q-29.
- **Report eval results as numerator/denominator with coverage.** Name the build, prompt version and data. Synthetic results are not evidence of real-clinic performance.
- **Live model calls only when the task needs them.** Otherwise use fakes, fixtures and the cache under `runs/`.
- **Clinical and language content you write is a draft.** Mark it pending review. You are not a clinical reviewer, and Telugu and Tamil need a native speaker. Cases stop at `auto_checked` until an independent person reviews them (D-28).
- **Before committing anything that could hold a key,** run `python -I tools/key_leak_check.py . <path-to-key-file>`. It must report `files containing the key: 0` and `key in git history: False`.

## Cloud sessions

Cloud sessions run in a Linux container as root, with no `.env`, no `../.venv`, no `../DATA`, no GPU and no Ollama. The runbook's Windows paths (`../.venv/Scripts/python`, `D:\Study\JANANI\…`, Edge) describe Aditya's laptop and don't apply here.

Set up and run the tests (checked on `claude/vibrant-archimedes-umbogz` in a cloud container: 495 passed, 2 skipped):

```bash
python3 -m venv .venv && .venv/bin/pip install -q -r services/api/requirements.txt -r tools/corpus/requirements.txt
```

```bash
mkdir -p runs && PYTHONPATH=services/api PDF_BROWSER=$PWD/tools/cloud/headless-chrome.sh .venv/bin/python -m pytest -q
```

- `pytest.ini` sets `--basetemp=runs/pytest-tmp`, so `runs/` must exist first. Without it, about 40 tests error.
- PDF rendering needs `PDF_BROWSER=tools/cloud/headless-chrome.sh`. That wrapper runs the pre-installed chrome-headless-shell with `--no-sandbox`. Always set it: without it the renderer finds `/usr/bin/google-chrome`, which stalls on `--print-to-pdf` here, and tests that render a PDF hang. Don't run `playwright install`.
- The web demo: `cd apps/web && npm install && npm run lint && npm run build`. To check it in a browser, start the API (`PYTHONPATH=services/api .venv/bin/uvicorn voicerx.app:app --port 8000`) and `npx next start -p 3000` in the background, then `NODE_PATH=$(npm root -g) node apps/web/scripts/e2e.mjs <screenshot-dir>`. Start the API with `VOICERX_FAKE_SPEECH=1` to cover the voice controls without spending Gnani credits. Stop the servers by PID (`ps -eo pid,args`), not `pkill -f`, which can match and kill the shell running it.
- Module commands need `PYTHONPATH=services/api`, for example `python -m voicerx.pipeline.run --help`.
- Gnani voice needs `GNANI_API_KEY`, preferably as an environment variable in the cloud environment's settings (never pasted in chat). A `GNANI_API_KEY=` line in the repo's ignored `.env` also works, but it disappears with the container. Without either, `/health` reports `speech: off` and the voice endpoints return 503. Each Prisma or Timbre call spends credits (rule 7): keep calls on demand, and report live results as worked or failed only (Q-04). The live check on 3 Nov (runbook Verification) confirmed both endpoints through our code. Timbre returns WAV with streaming header sizes, which `repair_wav_sizes` fixes (C-61).
- Real WhatsApp can't be tested from a cloud container, because Meta's webhook can't reach it. Test it with the fake Graph transport (`test_whatsapp.py`), or with the API's `WHATSAPP_GRAPH_BASE` pointed at a local stub. Test phone numbers must be unassignable, like `910000000001` (an Indian mobile can't start with 0).
- Provider keys exist only if they're set as environment secrets. Without them, don't attempt live Gemini, Groq or Gnani calls. Ollama is never available here. Cached and typed paths work offline.
- `tools/corpus/build_formulary.py` and the audio tools need `../DATA`, Whisper or the GPU. They can't run here.
- Commit the work you want to keep and push it to the session branch. The container is temporary, and `runs/` is never committed.
