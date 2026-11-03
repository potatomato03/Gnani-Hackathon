# Runbook

The running record of this project: what was done, every decision and judgement, why it was made, and where things stand. Read [Current status](#current-status) first.

## Keeping this file

- Update it in the same commit as the change it describes.
- Add new entries at the end of each section. Don't rewrite history: if something changes, mark the old entry `Replaced` and add a new one.
- This repo is public. Never add real patient details, the name of a real hospital, personal contact details or keys.

Every decision has a status:

| Status | Meaning |
|---|---|
| **Confirmed** | The team decided it, or it comes directly from a challenge rule. |
| **Assistant call** | The assistant decided it to keep work moving. The team hasn't confirmed it, and can overrule it. |
| **Proposed** | Recommended only. Not in effect until the team agrees. |
| **Open** | Waiting on someone. |
| **Replaced** | No longer in effect. A later entry explains why. |

## Current status

As of 2 Nov 2026. Deadline: **Tue 10 Nov 2026, 11:59 PM IST**.

| Area | Status | Next step |
|---|---|---|
| Registration | Not confirmed | Both members register and confirm eligibility |
| Gnani API key | In Aditya's file in the root folder and the ignored `.env`. Prisma v3.0 accepted it on 10 trial requests. | Find out what a request costs in credits (Q-03) |
| Repo | Implementation is on `aditya/extraction-report`; no push, merge or PR. `main` is unchanged. | Review the branch, then team merges when ready |
| Downloaded data | Done, 7 datasets in `../DATA`, about 5 GB. Only on one machine. | Share the folder with the teammate |
| Case families | 12 built, all `auto_checked` | Teammate review |
| Clinical review | Not started, no doctor booked | Book a doctor, ideally before 8 Nov |
| Language review | Not started | Find Telugu and Tamil readers |
| Formulary | 25 of about 100 rows, all `verified: false` | Hand-check each row, then extend |
| Audio | 22 of 25 clips rendered, all transcribed by Whisper. 3 wait on Gemini's daily limit. | Render the last 3, then listen to all of them |
| Extraction and report | Built and proven on all 25 typed cases with Groq: every expected flag fires, 33 of 33 medicines exact, no unsupported line. Doctor corrections and approval work end to end. Whisper text works for findings but not for medicine names written in Devanagari (Q-20). Prisma `codemix` writes brand names in Latin, which settles Q-20 on the 5 trial clips (D-93). | Transcribe the other clips with Prisma and run them; rerun Gemini after its reset for comparison |
| Mistral | Dropped. The key is rejected as invalid, and the plan couldn't be activated. | None |
| Local model | `qwen3:8b` and `qwen2.5:7b` in Ollama, stored in `models/ollama` in the root folder. First probe passed. | Compared with Gemini in Task 16 |
| Gemini text models | Overloaded on 2 Nov (HTTP 503) | Retry later. The planned client retries and falls back automatically. |
| Gemini key | Accepted by Google, stored in the ignored `.env` | None |
| Local transcription | Working on the GPU. `.venv` and `models` are in the root folder, on one machine only. | Teammate repeats the setup under [How to run](#how-to-run) |
| Gold notes | None, by design. They need real audio first. | Follows audio |
| Application code | Extraction/report backend, corrections, approval, PDF and FHIR implemented | Web, speech integration and patient agent remain outside this build |
| LLM | Groq `openai/gpt-oss-120b` is the working model, on two keys (D-85, D-88). Gemini (quota) and local `qwen3:8b` (safe but noisy) are fallbacks. | Compare Gemini once its daily limit resets |
| Evals | Typed and Whisper runs scored for Groq and the local model; see Verification. Prisma trial scored privately (D-91). | Score all Prisma clips, privately |
| Medicine knowledge | In Supabase and searchable: 46,540 chunks from openFDA labels, NLEM 2022 and Jan Aushadhi, embedded with bge-base on the GPU, plus 246,068 Indian products for brand lookup (D-94 to D-103, C-55 to C-60). 382 MB of the 500 MB free limit. Not used by the pipeline or any app yet. | Decide what the knowledge does first (Q-23); prefer single-medicine labels and the right route for brand questions |
| Follow-up agent | Demo built on `claude/vibrant-archimedes-umbogz` (D-104 to D-112): simulated WhatsApp chat in `apps/web` on an API in `services/api/voicerx/app.py`, with text, buttons and Gnani voice notes, started by approval. Synthetic. 7 of 7 demo-visit patient questions get the expected action (development data). Timbre and Prisma worked through our code in a live check on 3 Nov (4 calls). Red flags and wording await doctor and language review. | Team review and merge; first real WhatsApp run and call on a laptop (D-113, D-114, `docs/whatsapp-testing.md`); listen to the Timbre clips (Q-10); Q-25 to Q-29 |

## Decisions

### Project and process

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-01 | Use free or open LLMs for the first versions. Pay for Claude only if a test shows the need. | Prove the pipeline works before spending. | Aditya | Confirmed |
| D-02 | Commits and PRs carry no Claude co-author or attribution. | Requested directly. | Aditya | Confirmed |
| D-03 | Keep this runbook and update it as work happens. | Requested directly. | Aditya | Confirmed |
| D-04 | Internal planning docs stay out of this repo. | The repo is public, and those docs describe a real hospital visit. | Assistant | Assistant call |
| D-05 | When planning docs conflict, the newest planning README wins over the earlier design doc and roadmap. | It is the newest and calls its invariants and scope binding. | Assistant | Assistant call |
| D-06 | Work on the branch `aditya/data-setup`, not directly on `main`. | Only one worktree existed. A branch honours "my worktree" and leaves the teammate's `main` untouched. | Assistant | Assistant call |

### Data

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-07 | Build our own synthetic dataset. | The challenge says to use synthetic data, and no public dataset has Hinglish dictation with gold notes and Indian brands. | Team | Confirmed |
| D-08 | Use the five data groups, evidence from what was actually spoken, stage-level expected outputs, and allowed and forbidden claims for agent answers. | From ASTRA's review. It is stricter than the first draft of the method. | Team | Confirmed |
| D-09 | Start with 12 families, then at most 60: 20 development and 40 held-out. No separate validation split. Choose models on development data. | 120 families would take an estimated 50–80 hours, which doesn't fit the time left. Estimate, not measured. | Team | Confirmed |
| D-10 | If time runs short, shrink held-out to 20 rather than weaken review, and report the real count. | An unreviewed case isn't gold. | Team | Confirmed |
| D-11 | Formulary target is about 100 verified rows. Dose rules cover demo drugs only. | Matches the planning README, and a 2-hour doctor session can't cover 300 rows or 50 compositions. | Team | Confirmed |
| D-12 | A teammate checks most gold. The doctor reviews rules, drug cards, urgent wording and a sample of starter cases. | Gold records what was said, not whether treatment was right. | Team | Confirmed |
| D-13 | Freeze keyterms before writing held-out scripts, keep 3 or 4 Timbre voices for held-out audio, and include out-of-formulary brands in held-out scripts. | Stops test answers leaking into the system and inflating results. | Team | Confirmed |
| D-14 | Synthea is not used. ACI-Bench is optional. PriMock57 is optional and needs Gnani's answer first. | Synthea has no India configuration, needs Java, and would break the rule that histories come from reviewed cases. | Team | Confirmed |
| D-15 | DISPLACE-M, IndicVoices, Eka Medical ASR and Hinglish-CoT-Medical are not used. | The first is limited to its own challenge, the next two are real people's speech, and the last has no licence. | Assistant | Assistant call |
| D-16 | Downloads go in `DATA`, next to the repo, never inside it. | Aditya named the root folder. On Windows `DATA` and `data` are the same folder, and third-party data must not reach a public repo. | Aditya, Assistant | Confirmed |
| D-17 | Skip the 11 GB MUSAN download and use RIRS_NOISES. | RIRS_NOISES already contains MUSAN's 843 noise recordings. MUSAN still gets credited. | Assistant | Assistant call |
| D-18 | The Jan Aushadhi list stays local. | Its site requires emailed permission and credit before reproduction. | Assistant | Assistant call |
| D-19 | Never use the medicine dataset's side-effect or interaction text for drug cards. | It has no stated source. | Assistant | Assistant call |
| D-20 | Every formulary row starts `verified: false`. | A row isn't checked until a person checks it against a named source. | Assistant | Assistant call |
| D-21 | No synthetic case reuses the real visit's condition, medicine or wording. | Stops a "fictional" case from mirroring a real patient. | Assistant | Assistant call |
| D-22 | Phone numbers use `+91-00000-NNNNN`. | Indian mobile numbers don't start with 0, so these can't belong to anyone. | Assistant | Assistant call |

### Case format

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-23 | Case files are YAML, one per family. | People have to review them, and YAML with Devanagari is far easier to read than JSON. | Assistant | Assistant call |
| D-24 | Scripts follow Prisma's `codemix` style: Hindi in Devanagari, English in Latin, numbers as words. | That is the documented `codemix` output, and Timbre's Hindi examples use Devanagari. How Timbre reads mixed text is still untested. | Assistant | Assistant call |
| D-25 | `null` means not stated. Doses are text and can't be zero. | Unknown isn't zero, and 0.5 must never drift to 5. | Assistant | Assistant call |
| D-26 | "Once daily" stays a frequency unless the doctor gives a time. | Required by planning invariant 6. | Team | Confirmed |
| D-27 | Each family is a matched pair, except the three-visit family. | A pair shows what one change does. Paired cases stay in one split. | Team | Confirmed |
| D-28 | Cases stop at `auto_checked` until an independent person reviews them. | An author can't approve its own work. The checker enforces this. | Assistant | Assistant call |
| D-29 | `eval/gold/` stays empty until audio exists. Quotes point at the script for now. | Final evidence must come from what was actually spoken. Script quotes are valid for the typed test, where the script is the input. | Team | Confirmed |

### Proposed, not yet agreed

| ID | Proposal | Why | Status |
|---|---|---|---|
| D-30 | Hold doctor review and doctor trials before 8 Nov. | Diwali runs 6–10 Nov, over the plan's final days. | Proposed |
| D-31 | Decide on cuts on Wed 4 Nov, not Thu 5 Nov. | About 120 hours are available at best, against about 140 planned. Estimate, assuming half days on 8–10 Nov. | Proposed |
| D-32 | Publish the nominated post by Sat 7 Nov and skip the teaser. | Engagement on nominated posts decides the shortlist, and a teaser splits it. | Proposed |
| D-33 | Shorten the demo script. | A 20-second dictation plus ten other beats doesn't fit in 60 seconds. | Proposed |
| D-34 | Drop the Evon comparison. | The smallest quantized build is 18.1 GB, against 8 GB of VRAM and 15 GB of RAM on the development laptop. | Proposed |
| D-35 | Run the backend on a paid, always-on instance. | Render's free tier sleeps after 15 idle minutes, which would break a live call. | Proposed |
| D-36 | Use the free audio route below before spending Gnani credits. | See [Free audio research](#free-audio-research). | Confirmed, see D-40 |

### Replaced

| ID | Original | Replaced by |
|---|---|---|
| D-37 | Prepay about $50 for Claude on day one. | D-01. On free models first, this isn't needed yet. |
| D-38 | Keep the repo private. | D-04. The repo is public, so sensitive material stays out of it instead. |
| D-39 | Store downloads in `data/external/`. | D-16. Moved to `DATA` in the root folder. |

### Audio and transcription

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-40 | Build with Gemini TTS for audio and local Whisper for transcription, before spending Gnani credits. | Proves the pipeline for free. Aditya supplied the key and asked for the install. | Aditya | Confirmed |
| D-41 | Keep the Python environment in `.venv` and models in `models/`, both in the root folder. | Requested directly. It also keeps 5 GB out of the repo and leaves the global Python alone. | Aditya | Confirmed |
| D-42 | Use Whisper large-v3, pinned to an exact version. | MIT licence and the fullest model in that family. It fits an 8 GB GPU at `int8_float16`. | Assistant | Assistant call |
| D-43 | Get CUDA 12 libraries only from NVIDIA's official packages, pinned to the newest release with a Windows build. | The engine needs `cublas64_12.dll`. The other source found was a third-party bundle, and unofficial binaries shouldn't run on this machine. | Assistant | Assistant call |
| D-44 | Pin PyAV to 15.1.0. | PyAV 19 removes an option that faster-whisper 1.2.1 uses. | Assistant | Assistant call |
| D-45 | The Gemini key lives only in Aditya's own file and the git-ignored `.env`. Scripts send it as a header and never print it. | Keeps it out of git, logs, URLs and chat. | Assistant | Assistant call |
| D-46 | Run Whisper on the GPU with `int8_float16` and beam size 5. | Measured about 10× faster than CPU, and there was no time gain worth losing beam search for. | Assistant | Assistant call |
| D-47 | When one Gemini voice model hits its daily limit, switch to the next, and record the model on every clip. | Each model has its own allowance of 10 a day, so 25 clips can finish sooner. | Assistant | Assistant call |
| D-48 | Leave `gemini-3.1-flash-tts-preview` out of that list. | It rejects the style hint every request sends. Leaving it out keeps the set consistent. | Assistant | Assistant call |
| D-49 | Transcribe in chunks of at most 10 seconds, each decoded on its own. | Whisper caps each decode at 224 tokens and silently drops the rest. See C-17. | Assistant | Assistant call |
| D-50 | Flag a transcript as truncated if it ends in a broken character or a chunk nears the token cap. | Lost text must show up as a flag, not a clean-looking transcript. | Assistant | Assistant call |
| D-51 | Store the second Gemini key as `GEMINI_API_KEY_2` in `.env`. | Aditya supplied it. It's held in reserve for rate limits. Whether it shares a quota with the first key is unknown. | Aditya | Confirmed |
| D-91 | Transcribe with Prisma v3.0 on the REST endpoint, `format=codemix`, 16 kHz mono, language codes `hi-IN,en-IN` for Hinglish and one code otherwise (`tools/corpus/transcribe_prisma.py`). Prisma transcripts go to `data/eval/results/prisma*/` and their scores to `data/eval/results/scores/*prisma*`, both git-ignored; results are written up only in a private note in the root folder. | `codemix` is the style the scripts follow (D-24). The REST endpoint takes clips up to 30 seconds, which covers 20 of the 22 clips. Accuracy results can't go public until Gnani consents (Q-04). | Assistant | Assistant call |
| D-92 | Send no brand keyterms to Prisma. | A keyterm list pulls the transcript toward the listed products, so a name the doctor leaves ambiguous (only "Pan", where Pan 40 and Pan-D both exist) can come back as one specific product. The matcher then resolves it exactly and nothing is blocked: the checks can't catch an error that is already in the transcript. The trial showed this can happen (private note). Non-brand context (topic, speaker names) is untested. | Assistant, from the 5-clip trial Aditya asked for | Assistant call |
| D-93 | Settle Q-20 with Prisma `codemix` and no Indian-script aliases for now. | `codemix` writes English words, brand names included, in Latin script, which the Latin formulary can match; the trial clips bore this out (private note). Aliases stay an option if the full Prisma run finds names still written in Indian script. | Assistant | Assistant call |

### Extraction and report

Full design: [the spec](docs/superpowers/specs/2026-11-02-extraction-and-report-design.md).

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-52 | Two model stages, with a JSON of extracted words and terms between them. Stage 2 writes the report fields from that JSON. | Errors can be traced to transcription, extraction or report writing. | Aditya | Confirmed |
| D-53 | One approved record produces both a PDF and an ABDM FHIR bundle. | The two can never disagree. | Aditya | Confirmed |
| D-54 | The PDF carries medicine instructions in the patient's language, from fixed templates only. | A dose can't change in translation. | Aditya | Confirmed |
| D-55 | Code fills the medicine table and the current medicines list. The model writes the other sections. | Composition, strength, slots and dates must never come from a model. | Aditya, on recommendation | Confirmed |
| D-56 | Empty sections are left out and listed on one "Not discussed" line. | Gaps stay visible without padding the report. | Aditya, on recommendation | Confirmed |
| D-57 | Code checks both model stages, and blocking flags stop approval. | A model's output is a draft until code and a doctor accept it. | Aditya, on recommendation | Confirmed |
| D-58 | Use `gemini-3.8-flash` for both stages, on the free tier. | It is on the key, and free first applies (D-01). | Assistant | Replaced by D-59 |
| D-59 | Use `mistral-small-latest` (Mistral Small 4, Apache 2.0) first and `gemini-3.8-flash` as fallback, behind one model client. | Mistral's policy bars only health guidance "without proper qualification", and doesn't cover its open models run on your own servers, which gives a path to a real product. Gemini bars clinical practice outright. Two providers also survive one being down. | Aditya, by supplying a Mistral key | Replaced by D-70 |
| D-60 | Send Gemini text requests through the Interactions API. | Google returned "no longer available to new users" for `gemini-2.5-flash`, and recommends the Interactions API with `gemini-3.8-flash`. | Assistant | Assistant call |
| D-61 | A medicine's dose, timing, food, duration, start and route phrases must lie in its own mention, from its name to the sentence end or the next medicine. Otherwise they're flagged and not used. A correction may run into the next sentence. | Stops a dose being borrowed from another medicine. | ASTRA, checked by the assistant | Assistant call |
| D-62 | The medicine matcher compares whole tokens, scores how well each brand or alias fits, and never makes a fuzzy match exact. A wrong strength is unmatched. | "5" matched inside "2.5", suffixes such as Pan-D and Telma H were ignored, and a misspelling could become exact. | ASTRA, checked by the assistant | Assistant call |
| D-63 | A medicine whose speaker is unclear, or whose sentence has a first-person word such as मैं or "I", is blocked until the doctor confirms the order. | Patient speech must never become a prescription. The cost: a doctor who dictates "I'll start…" also has to confirm. See Q-19. | ASTRA, checked by the assistant | Assistant call |
| D-64 | Check 2 also checks subject, certainty and timing, and blocks a line that cites both absent and present items. | A relative's illness written as the patient's, or a suspected diagnosis written as definite, passed the earlier checks. | ASTRA, checked by the assistant | Assistant call |
| D-65 | `missing_quantity` covers continued medicines, which also go in the medicine table. A taper with a dose on every step is exempt, and each step keeps its time of day. | `fam-004` expects the flag on a continued medicine. `fam-010`'s taper would have been blocked, and would have lost "सुबह". | ASTRA, checked by the assistant | Assistant call |
| D-66 | The doctor clears flags by audited corrections through `resolve.py`. Each records who, when and why, and makes a new draft version. A blocking flag must be fixed, never just acknowledged. | Approval had no way to fix a flag. | ASTRA, checked by the assistant | Assistant call |
| D-67 | A draft freezes the patient, doctor and clinic records and the products it uses. Approval refuses a draft whose fingerprint no longer matches, and FHIR is built from the frozen copy. | The PDF and FHIR must show exactly what was approved, even if the formulary changes later. | ASTRA, checked by the assistant | Assistant call |
| D-68 | A rerun deletes the case's old files first. A missing transcript is reported as `missing_input`. Medicine history chains only from one visit to the next, never between variants a and b. | A stale report, a silent skip or a false history would each distort the scores. | ASTRA, checked by the assistant | Assistant call |
| D-69 | Treat the second Gemini key as a fallback, not as extra quota. | Both keys may belong to one Google project and share its limit. See Q-16. | ASTRA, checked by the assistant | Assistant call |
| D-70 | Use `gemini-3.8-flash` first and `qwen3:8b` through Ollama on the local GPU as fallback, behind one model client. Drop Mistral. Run the local model with an 8,192-token context, and never accept a reply that is cut off or overflows it. | Mistral's key was rejected (C-29). Gemini is free and the strongest option on these languages. The local model costs nothing, has no quota, works offline, and keeps transcripts on the clinic's machine, which answers Gemini's ban on clinical use (Q-15). It fits the 8 GB GPU; 12B models don't. | Aditya, on recommendation | Confirmed |
| D-71 | ASTRA builds the plan Native, one agent doing every task in order. Claude reviews the whole branch afterwards against the plan and spec. | Claude's usage limit was about to run out. One builder suits a plan whose tasks lean on each other's interfaces, and the review still comes from someone who didn't write the code. | Aditya | Confirmed |
| D-72 | PatientBox also carries official_note, defaulting to an empty string for callers that omit it. | The PDF must display the template's English-record-is-official notice separately from the unreviewed-translation note. | Builder | Assistant call |
| D-73 | Word-cue boundaries in the negation check include Unicode combining marks. | The cached clean fixture showed a false negation on Hindi text with combining marks. All ten sabotages still block. | ASTRA | Assistant call |
| D-74 | Whitespace normalisation keeps a same-length copy that preserves line breaks, so medicine mentions still end at a newline. | Normalising had erased the line boundary, which let a dose be borrowed from the next line. A regression test blocks it. | ASTRA | Assistant call |
| D-75 | Approval always validates the current draft first, and reuses an earlier approval's timestamp only for identical content and approver. | The CLI could reuse an old approval before checking a draft altered since. | ASTRA | Assistant call |
| D-76 | The PDF footer uses CSS page-margin boxes with escaped content, and spacing is tighter. | Live inspection found the footer overlapping content and a one-line second page. `fam-001-a` now fits one readable page. | ASTRA | Assistant call |
| D-77 | An exact medicine match needs the quoted name to resolve to the same product. Conflicting identities block, and ambiguous quotes stay ambiguous. | A model-supplied medicine name could disagree with its quote, or add a strength nobody said. | ASTRA | Assistant call |
| D-78 | Check 2 blocks a report line that states a side its citations don't support, and an unknown finding rewritten as positive. | The original word checks let both through. | ASTRA | Assistant call |
| D-79 | `run_cases` and the CLI take `--workers 1..4` (default 1) to run independent families in parallel. Visit order is kept, Ollama calls stay one at a time, and cache writes use unique temporary files. | Gemini retries took about 23 minutes for the first two cases. This changes scheduling only. | ASTRA | Assistant call |
| D-80 | A request that times out is retried on the same key like a 503. Only a refused or failed connection counts as an unreachable server. | One slow Gemini reply was disabling that key for the rest of the run (C-33). | Assistant | Assistant call |
| D-81 | Run the local-model comparison (`typed-local-1`) before the Gemini run, and retry Gemini once its latency recovers. Change prompts only after both runs, so each run is scored on one prompt version. | Gemini was taking 265 to 300 seconds for a one-word reply, which puts a 25-case run at over 4 hours and would switch it to the local model partway through. | Assistant | Replaced by D-82 |
| D-82 | Fix the stage 1 prompt now (`extract-v2`: laterality is null unless the quote names a side), and run both full comparisons on it. Run the local comparison first; Gemini follows once its latency recovers. | The laterality gap dominated the local run, 19 of 21 blocks on `fam-001-a` (C-35), so a comparison on `extract-v1` would measure that gap rather than the models. Gemini's run had only 2 of 25 cases and must be redone anyway. | Assistant | Assistant call |
| D-83 | A report may run to two A4 pages. Restore the original spacing (line height 1.45, wider heading gaps) that D-76 tightened to fit one page; keep D-76's footer fix. | Aditya: "it can be 2 pages long if need be". Readability matters more than one page, and the template already keeps sections and medicine rows whole across breaks. | Aditya | Confirmed |
| D-84 | Stop ASTRA's `typed-1` Gemini run and rerun it on `extract-v2`, two cases at a time, with Gemini only so it never falls back to the local model mid-run. | Aditya asked. That process had loaded `extract-v1` and the old timeout handling before C-33 and C-35 were fixed, so its results couldn't be compared. Gemini had recovered, finishing 13 cases quickly. | Aditya | Confirmed |
| D-85 | Add Groq as the second provider, between Gemini and the local model, using `openai/gpt-oss-120b` with a strict JSON schema. One OpenAI-compatible adapter (`openai_compat.py`) serves it, so Sarvam, Cerebras or OpenRouter would need only settings. A Groq schema rejection (HTTP 400 `json_validate_failed`) gets the usual one repair attempt. | Gemini was overloaded for most of 2 Nov, and the local model is slow and weaker. Groq's free tier allows 1,000 requests a day and 8,000 tokens a minute, about 2 calls a minute, and returned each extraction in about 4 seconds. | Aditya, by supplying a Groq key | Confirmed |
| D-86 | Rerun both models on `extract-v3` and `report-v2` before comparing them, and cap the local model's reply at 4,096 tokens. Score and explain every unexpected block per run. | The first Groq run (`extract-v2`) showed model errors a clearer prompt can prevent (C-37), and the local run was still on `extract-v2` and stuck in a loop (C-38). A fair comparison needs both on the same prompts. | Assistant | Assistant call |
| D-87 | The doctor can also correct report lines: `edit_line` rewrites a line (it keeps its citations) and `remove_line` drops one, each audited and making a new version, from the CLI as `--edit section:index=text` and `--drop section:index`. A line's flags clear when it is edited or removed; a finding's flags clear once no untouched line uses it. Later lines' flags are renumbered after a removal, and an emptied section moves to "Not discussed". | `resolve` could only correct medicines, so any blocking flag on a finding or line (negation, side, certainty, subject, unsupported) made a draft impossible to approve. D-66 says the doctor clears flags by audited corrections. Adding a new line is left to the review screen. | Assistant | Assistant call |
| D-88 | Use both Groq keys, `GROQ_API_KEY` then `GROQ_API_KEY_2`, in one client. | Each key belongs to its own Groq organisation with its own 200,000-token daily limit; a full-size request on the second key succeeded while the first was spent (C-42). | Aditya, by supplying a second Groq key | Confirmed |
| D-89 | Two more doctor corrections: `add_line` writes a line into a section citing findings (`--add "section=text\|x1,x2"`), and `dismiss_item` rules out a finding no line uses (`--dismiss x5`). Each clears that finding's flags, is audited and makes a new version. | A blocking `omission` (stage 2 left a finding out) had no correction at all, so such drafts could never be approved (C-47). This extends D-87. | Assistant | Assistant call |
| D-90 | A rerun or a new approval never deletes signed or versioned files. `approved_report.json`, `report_approved.pdf`, `fhir_*.json` and `draft_report.v<N>.json` move into a `superseded-<UTC time>` folder inside the case folder. | The audit trail must survive reruns and re-approval (C-45, C-46). | Assistant | Assistant call |

### Medicine knowledge

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-94 | Give the system medicine knowledge by retrieval: chunk trusted sources, store them in a free vector database, and let the model look them up. No model is trained. | Aditya wants the system to know Indian medicines and the conditions they treat as it scales. Retrieval is cheaper than training, easy to update, and lets every answer cite its source. | Aditya | Confirmed |
| D-95 | Sources: openFDA drug labels (CC0) for uses, doses, warnings and interactions; NLEM 2022 and the Jan Aushadhi list for Indian treatment categories. The Indian Medicine Dataset only decides which generics are sold in India and is not chunked. Not used: that dataset's description, side-effect and interaction columns, and Hugging Face sets with no licence or source (such as `dmedhi/indian-medicines`), which look scraped from a pharmacy site. The National Formulary of India is paid and under copyright. | No free source pairs Indian medicines with what they treat under a clear licence. US labels are public domain and detailed; the Indian lists add what India uses. | Assistant; Aditya approved the 1.77 GB download | Confirmed |
| D-96 | Keep one openFDA label per ingredient set and route, and only where every ingredient is sold in India. The label kept is prescription over OTC, then the one with most sections, then the newest. Indian and British names are mapped to US names first (`tools/knowledge/names.py`: paracetamol to acetaminophen, salbutamol to albuterol, and others). | The export holds many near-copies of each generic. Without the name map, most Indian medicines would never find their label. | Assistant | Assistant call |
| D-97 | Chunk each label by section (uses, dosage, contraindications, warnings, interactions, special populations, side effects, overdose, and the OTC sections), at sentence ends, up to 1,500 characters. Every chunk opens with the medicine, route and class, and carries its DailyMed link, label date, licence and a note that it is a US label. Clinical studies, pharmacology and packaging are left out. NLEM gives one chunk per medicine with all its categories; Jan Aushadhi one per treatment group, without surgical consumables. | A section is what a question asks for ("interactions of telmisartan"), and the heading makes each chunk make sense on its own. 1,500 characters leaves room inside a 512-token embedding window. | Assistant | Assistant call |
| D-98 | Downloads and chunks stay in `../DATA/knowledge`, outside the repo; only the code is in the repo. | Jan Aushadhi needs PMBI's permission before public reuse, NLEM states no licence, and the labels are 1.77 GB. | Assistant | Assistant call |
| D-99 | Retrieved knowledge never writes report lines. It may only raise review flags for the doctor or support cited answers to questions. | Every report line must cite what the doctor said (the evidence rule behind every check). A retrieved fact in the report would be a claim the doctor never made. | Assistant | Proposed |
| D-100 | Store the knowledge in Supabase (Postgres with pgvector, free plan) instead of Chroma: chunks and their vectors in one table, the Indian brand list as an ordinary table beside it. The publishable and secret keys live in Aditya's files in the root folder and the ignored `.env`; the secret key stays on the backend. | One database holds both exact lookups (brand to ingredients) and vector search, can combine vector and text search in one query, and is reachable by the teammate and a deployed demo. About 200–250 MB fits the 500 MB free limit with a 384-dimension model. Free projects pause after a week unused, so resume it before the demo. | Aditya | Confirmed |
| D-101 | Embed with `BAAI/bge-base-en-v1.5` (768 dimensions), run locally through fastembed 0.9.1 (Qdrant's ONNX build, MIT), on the CPU. Chunks are embedded as passages without a prefix; questions must use the same model's query mode. Embedded shortest first in batches of 16. Vectors, chunk ids and a model record go to `../DATA/knowledge/embeddings/bge-base-en-v1.5/`; the model is in `../models/fastembed`. | Aditya chose bge-base over bge-small for better retrieval. fastembed avoids installing PyTorch. On this CPU 256 chunks took 148 seconds in batches of 256 and 104 seconds sorted in batches of 16, so the full run takes about 3.5 hours. 1 chunk in 256 sampled runs past the model's 512 tokens and loses its tail. | Aditya (model); Assistant (runtime) | Confirmed |
| D-102 | In Supabase, store the vectors as `halfvec(768)` (pgvector's 16-bit type) with an HNSW index on cosine distance. | 768 dimensions at full precision come to about 100 MB of vectors plus an index of similar size, which with the text and the brand table gets close to the 500 MB limit. Half precision halves both, with negligible effect on retrieval. | Assistant | Confirmed (Aditya approved the design) |
| D-103 | Supabase tables: `knowledge_chunks` (one row per chunk with its metadata, a `halfvec(768)` embedding with an HNSW cosine index, and a stored English full-text column with a GIN index) and `indian_products` (the Indian Medicine Dataset's current allopathic products: name, manufacturer, pack, composition, normalised ingredient keys; not its description, side-effect or interaction columns). One SQL function, `match_chunks`, merges vector and keyword results by reciprocal rank fusion, keeps at most two chunks per label, and can filter by source. Row-level security on, with no policy for the publishable key, so only the backend reads. | Keyword search catches what vectors miss ("diabetes" for "Anti-Diabetic", C-58); the per-label cap stops near-identical labels filling the results. About 230–260 MB in all, by estimate. | Assistant | Confirmed (Aditya approved the design) |

### Follow-up agent

Research: [docs/research/followup-agent.md](docs/research/followup-agent.md). Design: [the spec](docs/superpowers/specs/2026-11-02-followup-agent-design.md).

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-104 | The follow-up agent is our own backend behind a channel interface, connected to WhatsApp through the Cloud API, not Meta Business Agent. | Meta Business Agent excludes the Health vertical; a clinic's own task-specific bot is allowed under WhatsApp's January 2026 AI rule (research findings 1 and 2). | Assistant | Proposed |
| D-105 | The demo is a simulated WhatsApp-style chat on synthetic patients; the real WhatsApp adapter stays off. | The challenge bans real phone numbers, and seed numbers can't receive WhatsApp. | Devansh (session user) | Confirmed |
| D-106 | Code builds the follow-up plan from the approved report only: summary at approval, a tolerance check two days after a new medicine starts, a mid-course check for courses of 7 days or more, an end-of-course check, and a review reminder two days before a doctor-confirmed review date. Same-day touches merge, named for the later stage. | No model sets a date or time; one-way reminders alone showed no effect in an Indian trial, so each touch asks a question. | Assistant | Assistant call |
| D-107 | Scheduled messages only between 09:00 and 20:00 IST, at most one a day and five per visit; after two unanswered check-ins the plan stops and the doctor gets a `no_response` task. Patient messages are answered at any hour. | Reminder fatigue and drop-off in the research (Kilkari, notification fatigue). | Assistant | Assistant call |
| D-108 | Warning signs are rules first, from `data/rules/red_flags.yaml` (Hindi in Devanagari and Latin, and English; negation handled). Any match sends the fixed urgent message, opens an urgent task and ends routine check-ins. A model may only add warning signs, never remove one. The list is a draft pending doctor review. | Under-triage is the worst failure; patients play symptoms down. | Assistant | Proposed |
| D-109 | Every message to the patient passes one gate: the approved report and its fingerprint, consent (`followup_whatsapp`) and STOP, sending hours, and exact fixed text for the summary, medicine answers and the urgent reply. The first message says it is an AI and offers DOCTOR and STOP. The agent answers only how, when or how long to take a medicine the record names, word for word from its fixed row; anything else, and any request to change a medicine, goes to the doctor. | Wrong medical advice is the main fear in every source. The gate turns a tampered dose, an uncited answer or a softened urgent reply into a refusal (sabotage tests). | Assistant | Assistant call |
| D-110 | Demo visits run offline through the real pipeline from saved stage outputs (`services/api/tests/fixtures/<case>/`, replayed by `voicerx/fixture_client.py`): `fam-001-a`, `fam-004-a` and `fam-010-a`. `fam-004-a`'s expected `missing_quantity` is cleared by two audited doctor corrections (one tablet, once daily) before approval. `fam-010-a`'s review date (7 days) is set as doctor-confirmed in the demo setup, never parsed from report text. | The demo must work with no model key, and must show the real checks and corrections, not a mock. | Assistant | Assistant call |
| D-111 | Voice notes use Gnani over REST (`voicerx/ingest/gnani.py`): Timbre v3.0 speaks clinic messages, voice `Chetana`, language `auto` for Hindi (mixed Devanagari and Latin) and `en-IN` for English; Prisma v3.0 `codemix` transcribes patient voice notes with hints `hi-IN,en-IN` or `en-IN,hi-IN` and no keyterms (D-92). Calls are on demand only: a clinic message is voiced when someone taps Listen, and each exact text is synthesised once and cached in the ignored `runs/followup-demo/audio/`; a patient voice note is transcribed when sent. A recorded voice is held in memory and never written to disk; only its transcript is kept. A "synthetic voice note" turns typed text into a Timbre patient voice (`Shubham`) and sends that to Prisma, so the demo needs no real voice. One request at a time, 429 retried. The transcript goes through exactly the same rules as typed text. | Devansh (session user) chose on-demand, cached calls and both voice-note routes; Gnani's docs give the endpoints. Credit cost is unknown (Q-03), and the challenge bans recorded calls. | Devansh (session user), Assistant | Confirmed |
| D-112 | Approval starts follow-up. Any current `approved_report.json` under `runs/` that matches its fingerprint is a follow-up visit (`agent/visits.py`); consent is read from the frozen record snapshot. `voicerx.approve` takes `--review-date YYYY-MM-DD` (written to `followup.json` beside the report, with who confirmed it) and `--followup` (sends the visit summary at once). The API lists every approved visit (`GET /visits`) and starting one twice resumes the same conversation. The demo fixtures are ordinary approved visits marked `source: demo`. | Connects the doctor's approval to the patient follow-up, and answers Q-25 for the CLI: the review date comes from the doctor, never from report text. | Devansh (session user), Assistant | Confirmed |
| D-113 | Real WhatsApp, for private testing only. `agent/whatsapp.py` connects the same conversation core to Meta's Cloud API (test number, Graph API v26.0): webhook in, signed with the app secret; text, reply buttons and Ogg Opus voice notes out. Only numbers in `WHATSAPP_TEST_NUMBERS` are served. A number lives only in memory, and a conversation stores a keyed hash of it. A phone sends `JOIN <visit code>` to start a synthetic visit. Clinic messages leave only after the gate and only inside WhatsApp's 24-hour window; otherwise they wait. Through a tunnel the API answers only the webhook. The server runs on a laptop behind a Cloudflare quick tunnel (`docs/whatsapp-testing.md`). | Devansh asked to run the agent on WhatsApp. The challenge bans real phone numbers, so D-105 still governs the submitted demo and video: they stay simulated. | Devansh (session user) | Confirmed |
| D-114 | WhatsApp voice calls, user-initiated only: the patient calls the clinic's WhatsApp number. The `calls` webhook brings an SDP offer, and `agent/webrtc_call.py` (aiortc) answers with `pre_accept`, then `accept` once WebRTC connects. `agent/call.py` speaks a fixed greeting that says it's an AI, then takes half-duplex turns: energy VAD cuts one utterance (0.8 s silence, 25 s cap), Prisma REST transcribes it, and the transcript goes through `receive` with the same rules and gate. Timbre speaks the gated replies, cached by text, and they also go to the chat as text. The call ends after a warning sign, STOP, DOCTOR, 6 turns, 5 minutes or two silences. One call at a time. Unknown, unbound or stopped callers are rejected. Call audio is never written. | Devansh asked to embed WhatsApp calling. Meta's docs (3 Nov): user-initiated calls are free and allowed on test numbers; business-initiated calls aren't available from US numbers such as the test number. No barge-in and REST speech-to-text per turn keep it simple; streaming Prisma is a later improvement. | Devansh asked; design is an Assistant call | Assistant call |
| D-115 | The model reads, code speaks. When a model key is set, every free-text message and voice-note or call transcript is also read by a model (Gemini, then the configured fallbacks) into a fixed `Understanding`: an intent, the check-in answer, an approved medicine id, a language, warning-sign ids, and a quote copied from the message (`agent/understand.py`, prompt `understand-v1`). Code validates every value against the conversation and drops what doesn't fit; a reading whose quote isn't in the message is ignored. The rules still run first: a rule warning sign, STOP or DOCTOR is never overruled, and a model warning sign can only raise urgency. Code then acts through the existing paths (check-in answer, approved-row answer, doctor task), and every reply is still fixed template text through the gate (D-109); a change request is always escalated. A model reading "stop" asks the patient to confirm with buttons; the word STOP still stops at once. Chat calls fail fast (one try, 15 s timeout, a busy model rests 60 s), so with no key, a busy or exhausted provider, the patient gets today's rule-based reply. | Devansh asked for a bot patients can talk to in their own words. The original design planned free text to go to a model with a fixed schema (spec, `agent/route.py`). Keeping replies fixed keeps D-109's protections; the gap is now only what the templates can say (Q-30). Live check 4 Nov: medicine question, change request, side effect with breathlessness, and a prompt-injection message were all read correctly in about 5 s each. | Devansh asked; design is an Assistant call | Proposed |

## Judgement calls

Places where a request or a source could be read more than one way.

| ID | Situation | What was done | Why |
|---|---|---|---|
| J-01 | "Create a tree for us" | Built the folder layout from the planning README and committed it. | It was asked for alongside a repo link and a co-author instruction, so a commit was expected. |
| J-02 | "Push it in my worktree" | Used a new branch in the existing clone. | No other worktree or branch existed. See D-06. |
| J-03 | "Create a DATA folder" | First used `data/external/`, then moved to `D:\Study\JANANI\DATA` once Aditya said the root folder. | The root instruction made the intent clear. |
| J-04 | Git had no identity set | Set AdityaRaj80 with the GitHub noreply address, in this repo only. | Keeps a personal email out of public history and leaves global settings alone. |
| J-05 | Approval to edit is not approval to push | Left edits uncommitted until asked. | Pushing to a shared repo needs its own approval. |
| J-06 | Is a public dataset allowed? | Treated silence in the rules as permission to check, not permission to use. | The ban on real identifiers and recorded calls still applies, and so does each licence. |
| J-07 | Does the EULA apply to the challenge? | Treated it as possibly applying, and logged a question. | The registration form links it. It also bans demonstrating the product, which the challenge requires, so it may not fit. Assuming either way is a risk. |
| J-08 | Clinical content in the 12 cases | Used ordinary doses and plausible cases, and marked clinical review pending. | The assistant is not a clinical reviewer. |
| J-09 | Telugu and Tamil scripts | Written by the assistant, marked language review pending. | Neither has had a native speaker's review. |
| J-10 | Jan Aushadhi data | Read the public page and used its own Download CSV. Didn't touch the admin routes found in the site's code. | Only the public export was needed. |
| J-11 | Windows filename from that export contained `/` and `:` | Renamed the save target rather than clicking again. | Avoided stacking more save prompts. |
| J-12 | "Keep the path same as the root folder" | Installed into `D:\Study\JANANI\.venv` and `D:\Study\JANANI\models`. | Aditya calls that folder the root. |
| J-13 | Asked to install and download, not to test | Also ran one clip through Gemini TTS and Whisper. | An install isn't proven until it runs. This used one free request and no Gnani credits. |
| J-14 | The key file wasn't in the older `AIza` format | Tested it with a single model-list call instead of guessing. | Google accepted it. |
| J-15 | ASTRA's review said to keep two Gemini stages | Kept the two stages, with Mistral first. | ASTRA wrote before Mistral replaced Gemini as the first provider (D-59). |
| J-16 | How bare brand names resolve | Followed the formulary's aliases. "Telma" means Telma 40 and "Amlong" means the 5 mg product, while "Pan" stays ambiguous because both Pan products carry that alias. | No special cases in code. The aliases are unverified, and get checked with the formulary rows. |
| J-17 | "Install the Ollama model, use this root folder only", while `qwen2.5:7b` already sat in the default folder on C: | Moved Ollama's model folder to `D:\Study\JANANI\models\ollama` and copied `qwen2.5:7b` there too, so it still works. Left the old copies on C: rather than deleting them. | The setting changes where Ollama looks for every model, so the old one had to come along. Deleting the C: copies (about 9 GB) is Aditya's call. |
| J-18 | Is `qwen3:8b` good enough to be the fallback? | Accepted it, after a probe on two typed scripts with a forced JSON schema. All 26 quoted phrases came back exactly, and `fam-008-a`'s two medicines had the right dose, timing and duration. It marked "वज़न कम नहीं हुआ" (no weight loss) as present, and filed the medicines as diagnoses as well. | The probe used a short prompt, not the plan's. The negation slip is the kind of error Check 1 blocks, so a weaker model costs more flags, not wrong reports. Task 16 measures it properly. |
| J-19 | `fam-001-a`'s typed run raised an unexpected `laterality_mismatch`. | Counted it as a model error that Check 1 rightly blocked, not as a defect in the checks. The script says "tonsils normal". The model added "bilateral" and wrote "Bilateral tonsils normal", reading a side into the plural. | The flag is correct. The fix belongs in the stage 1 prompt (set laterality only when a side is spoken), and waits until both runs are scored (D-81). |
| J-20 | Which Groq model? The key offers `openai/gpt-oss-120b` and `qwen/qwen3.8-27b`. | Chose `gpt-oss-120b`. On `fam-001-a` and `fam-008-a` with the real `extract-v2` prompt and schema it returned valid JSON both times, no invented sides, both negations, and every medicine phrase verbatim. Qwen failed Groq's JSON check once, and rewrote "Dolo six fifty" as "Dolo 650", which isn't a quote. | Through the full pipeline, `gpt-oss-120b` gave `fam-001-a` no flags and `fam-008-a` exactly its two expected flags, in 32 seconds for both. |
| J-21 | `fam-003-a` on `extract-v3`: "X-ray of the left wrist shows no fracture". The model set the side to left but quoted only "no fracture", so the side check blocked it. | Counted as a model quoting error that was rightly caught, not a check defect. | The side is in the sentence, but "pain in the right wrist, sorry, left wrist" shows why the check must find the side in the quote itself, not anywhere in the sentence. A later prompt can ask for quotes that include the side. |
| J-22 | `typed-local-2` `fam-008-a`: the model gave the whole sentence "Pan एक गोली सुबह खाली पेट, दो हफ़्ते" as the spoken name, while its verified name quote was "Pan". It came back unmatched, not ambiguous. | Test-first: when the spoken name matches nothing but contains the verified quote, the quote decides. A spoken name that contradicts its quote ("Dolo 500" against "Dolo six fifty") stays unmatched; the sabotage test caught a first, looser version of this rule. | Still blocked either way, but the doctor now sees "Doctor to choose: Pan 40 or Pan-D" instead of "Unrecognised medicine". |
| J-23 | "Merge it into my branch" (Devansh, session user), with the session branch cut from `main` and the backend only on `aditya/extraction-report` | Merged `origin/aditya/extraction-report` into `claude/vibrant-archimedes-umbogz` and built the follow-up demo on top. Aditya's branch was not changed or pushed. | The follow-up agent needs the approved report, corrections and patient-language templates. |
| J-24 | "Now how do we actually integrate it with our application" | Asked; Devansh chose "approval starts follow-up" over the full doctor web flow or a real WhatsApp connection. Built that (D-112). | The phrase could mean any of the three; they differ by days of work. |
| J-25 | "Now how do I run it on whatsapp?" | Asked. Devansh chose private testing on the team's phones (the demo stays simulated), the Meta Cloud API test number, and his laptop behind a tunnel. Built that (D-113). | It conflicted with D-105 and the challenge's ban on real phone numbers, and it could have meant only running the simulated demo. |
| J-26 | "Push this to my Devansh tree" (Devansh, 4 Nov), with no Devansh branch on the remote and Supabase key files dropped into an unignored `Supabase secret/` folder in the repo | Created `devansh/whatsapp-nlp-bot` from `claude/vibrant-archimedes-umbogz` and pushed it, after ignoring `Supabase secret/` and `*.env.txt`. The keys went only into the ignored `.env`. | "Tree" read as a branch of Devansh's own; a bare `devansh` branch would block later `devansh/*` names. Pushing the key folder would have broken hard rule 2. |

## Corrections

Mistakes and wrong statements, and how each was fixed.

| ID | What went wrong | Fix |
|---|---|---|
| C-01 | Said the Indian Medicine Dataset showed no clear licence. | Its repo is MIT, though the data's origin isn't stated. Corrected in the docs. |
| C-02 | Listed the ABDM guide's licence as not confirmed. | Its package states CC0-1.0. Corrected. |
| C-03 | Four checker tests changed only one variant while the spec change applied to both. One passed for the wrong reason. | Added a helper and made that test assert the exact issue and variant. |
| C-04 | The formulary build failed on `Pan 40 Tablet`, because the dataset says `PAN 40 Tablet`. | Wrote a failing test, then made the lookup ignore case. It also now refuses discontinued products. |
| C-05 | Medicine references were only checked on the base spec, so a product swapped in by a variant went unchecked. | Wrote a failing test, then moved the check to run per variant. |
| C-06 | The `omit` feature had no test. Found by disabling each checker rule in turn. | Added a test. All 23 sabotaged rules are now caught. |
| C-07 | A checksum run reported failures. The cause was Windows line endings in the list, not the data. The push also went ahead, because it wasn't tied to that check. | Stripped the line endings and reran: all 10 match. No data changed. |
| C-08 | The first Jan Aushadhi download seemed to vanish. It was waiting on a save prompt, which Aditya answered. Two copies landed in the root folder. | Confirmed they were identical, filed one and removed the other. |
| C-09 | A `cd` left the shell inside the downloads folder. | Moved out before running any code. Downloaded files are treated as data and never run. |
| C-10 | Transcription failed on both GPU and CPU, because faster-whisper 1.2.1 passes an option PyAV 19 no longer accepts. Its own requirements allow that version. | Confirmed the cause in the source, then pinned PyAV to 15.1.0. |
| C-11 | The newest `nvidia-cublas-cu12` release has no Windows build, so the GPU couldn't load `cublas64_12.dll`. | Pinned 12.9.2.10, the newest official release with one. |
| C-12 | Gemini was asked for 16 kHz, as its docs describe, and returned 24 kHz. | Noted. Clips must be resampled before they reach Prisma. |
| C-13 | Script lengths were estimated at 2.2 words a second. The first clip measured 2.8, so the 10–40 second estimate is a little long. | Durations will be measured from real audio. |
| C-14 | The first transcription took 50 seconds for a 22-second clip, which looked like a GPU fault. It was first-run setup. | Measured repeat runs before quoting a speed: 8 seconds. |
| C-15 | The render tool kept retrying a daily limit for 7 minutes. It expected "PerDay" in the error, but Google wrote the limit in plain words and put the wait in a `Retry-After` header. | Fetched the real error with one probe, then made the tool recognise both, test-first. |
| C-16 | The fallback voice model `gemini-3.1-flash-tts-preview` failed with "Speech metadata is not supported". | Removed it from the list. See D-48. |
| C-17 | Seven transcripts stopped mid-sentence. The audio was complete, and Whisper had stopped each decode at 224 tokens. Raising `max_new_tokens` didn't help, and neither did voice-detection settings in normal mode. | The third hypothesis worked: decode each chunk of 10 seconds or less separately. Words recovered rose to 1,223 of 1,250. |
| C-19 | The first Mistral request failed with "Rate limit exceeded". Its headers showed a limit of 0 requests a minute, so the account has no active plan. It wasn't a usage problem. | Recorded. The model client treats a limit of 0 as no quota, and moves to Gemini without retrying. |
| C-20 | Gemini extraction probes timed out after 3 minutes, then returned HTTP 503 "high demand" on `gemini-3.5-flash` and `gemini-3.8-flash`, by both request styles. | Stopped probing after four requests. The model client retries 503s, then falls back. |
| C-18 | Google's error at 12:49 said the daily limit would reset in about 40 minutes. At 1:34 PM it still refused, and said to retry in about 24 hours. The cause is unknown. | The last 3 clips render on the next attempt. Not probed further, to avoid spending tomorrow's allowance. |
| C-21 | The plan's matcher let "5" match inside "2.5", ignored suffixes such as Pan-D and Telma H, and could make a fuzzy match exact. Found by ASTRA. | Rewrote it on whole tokens and fit scores, with a test for each case. See D-62. |
| C-22 | The plan raised `missing_quantity` only for new or changed medicines, though `fam-004` expects it on a continued one. It would also have blocked `fam-010`'s taper, and dropped each step's time of day. Found by ASTRA. | Covered continued medicines and exempted full tapers. Added `when` to taper steps in the contracts and the case format. See D-65. |
| C-23 | Check 2 missed subject, certainty and timing errors, and a line mixing "no fever" with a present finding passed its negation rule. Found by ASTRA. | Added those checks, each with a test. See D-64. |
| C-24 | The plan had no way to fix a flag before approval, never verified the fingerprint, and built FHIR from live data. Found by ASTRA. | Added doctor corrections (Task 10b), the fingerprint check, and the frozen snapshot. See D-66 and D-67. |
| C-25 | A failed rerun could leave the old report in place, a missing Whisper transcript wasn't handled, and variants a and b could chain like visits. Found by ASTRA. | Added each fix with a test. See D-68. |
| C-26 | Task 16 ran the pipeline from `services/api`, where `../.venv` doesn't exist. Found by ASTRA. | It now runs from the repo root with `PYTHONPATH=services/api`. |
| C-27 | Check 2's negation rule would have blocked `fam-001`'s follow-up, "come back if not better in three days". Found by checking the plan against the case files. | A negation in the line is allowed when the cited quote has one too. Added a test. |
| C-28 | Task 16 expected `missing_quantity` only on `fam-005-a`. It left out `fam-004-a`, `fam-004-b`, and `unmatched_product` on `fam-008-b`. | Listed every expected flag from the case files. |
| C-29 | Aditya couldn't activate Mistral's free plan. A test of the saved key returned HTTP 401 "Invalid API Key" for both the model list and a chat request. | Dropped Mistral. See D-70. Q-18 is closed. |
| C-30 | The first local probe used a 16,384-token context. Ollama put 20% of the model on the CPU, and it ran at 10 tokens a second, 187 seconds for one stage. | At 8,192 tokens it runs fully on the GPU at 16.5 tokens a second, about 50 seconds a stage. The longest typed script is about 300 tokens, so 8,192 leaves room. |
| C-31 | Setting `OLLAMA_MODELS` didn't move Ollama's models. The Windows app keeps its own model location in its settings database and passes that to the server, so the first download still went to C:. | Stopped the app, backed up its settings, set the location to the root folder, copied the models there, and restarted it. The server log confirms the new folder. The `OLLAMA_MODELS` user variable is still set, to the same folder. |
| C-32 | Pytest could not create its temporary directory inside the Windows tool sandbox. | Added pytest.ini with a repository-local ignored runs/pytest-tmp directory. Tests remain unchanged. |
| C-33 | The transport returned status 0, "unreachable", for a timeout too, and the client then marked that key exhausted for the whole run. On 2 Nov a one-word Gemini request timed out at 300 seconds on the first key and took 265 seconds on the second, which is how `fam-001-b` ended up on key 2. | Test-first: a timeout now returns 504 and is retried on the same key. A refused connection is still unreachable. See D-80. |
| C-34 | ASTRA's `typed-1` run kept going after ASTRA stopped, with no log, waiting on Gemini. It had finished 2 cases in about 30 minutes. | Left it running, because stopping another agent's process wasn't permitted, and started the local run separately with a log file. `typed-1` gets rerun once Gemini recovers, from the cache. |
| C-35 | The stage 1 prompt asked the model to distinguish sides but never said when to leave laterality empty, and the schema makes every field present. `qwen3:8b` put "bilateral" on all 9 items of `fam-001-a`, giving 19 `laterality_mismatch` blocks; Gemini did it once, on "tonsils". Check 1 caught every one. | Test-first: `extract-v2` says laterality is null unless the quote names a side, and that a plural body part is not one. The local model's `fam-001-a` went from 21 blocks to 1, a real `certainty_mismatch` on a provisional diagnosis. See D-82. |
| C-36 | Check 1 rejected a phrase the model copied with its closing mark, such as "…से ज़्यादा नहीं।", because a mention ends just before the mark. It blocked Asthalin's and Wysolone's timing in `fam-010-a` as `phrase_not_bound`. | Test-first: trailing marks and spaces are trimmed from each phrase before binding. |
| C-37 | The first Groq run (`typed-groq-1`, `extract-v2`) had all 7 expected flags but 20 unexpected blocks and 20 of 33 medicines exact. Besides C-36 and C-39, every block was a model error that a check rightly caught: strengths ("forty", "ten", "five") given as doses; timing and food joined in one phrase; Telugu phrases translated into English; a whole sentence given as a medicine name; "पैर में दर्द नहीं जा रहा" (pain doesn't go to the leg) read as "leg pain persisting"; "SLR negative" kept as a present item; an invented "left" on "no fracture"; and stage 2 writing "Provisional:" on four stated diagnoses. No wrong value reached a draft unflagged. | Test-first prompt changes: `extract-v3` says the dose is never the strength, each field stays separate, the name quote is only the name, never translate, and a negative test is an absent item. `report-v2` never writes "Provisional" for a stated item. |
| C-38 | The local model looped on `fam-009-b` for over 30 minutes, generating until its context filled, then again on the repair attempt. | Test-first: Ollama replies are capped at 4,096 tokens, so a loop is cut off, rejected and repaired within a few minutes. |
| C-39 | `fam-011-v3` continues Telma with no dose ("Telma forty चालू रखें"), which D-65 flags as `missing_quantity`, as in `fam-004`. The case file didn't list the flag, so a correct block counted as unexpected. | Added `expected_flags: [missing_quantity]` to the variant; the checker passes. |
| C-40 | Check 2 blocked "LDL 160 mg/dL" in `fam-004-b`'s results as a medicine dose written into a report line. "mg/dL" is a lab concentration. | Test-first: a unit followed by "/" is not a dose. "Paracetamol 500 mg" in a line still blocks. |
| C-41 | The full test suite hung for over 10 minutes. A headless Edge stalled during a PDF test; Python killed it at the 90-second timeout, then waited forever on output pipes its helper processes still held. The same could freeze a pipeline run. | Test-first: Edge runs with no captured output, and on timeout the whole process tree is killed and the render fails with "timed out". |
| C-42 | The second Groq run stopped after 15 cases: "tokens per day (TPD): Limit 200000, Used 197639". The two Groq runs and the probes used the whole free daily allowance. The client recognised the daily limit and stopped each case cleanly, as designed. | The other 10 cases run from the cache once the allowance frees. Each full typed run costs about 125,000 Groq tokens, so plan one Groq run a day. |
| C-43 | In `typed-groq-2` `fam-008-a`, "Acid reflux लग रहा है" (seems like acid reflux) came back as a stated complaint, and nothing flagged it, because the item and its line agreed. A suspected diagnosis read as definite is the error D-64 targets. | Test-first: Check 1 blocks `certainty_mismatch` when a present, stated item's quote holds a hedge such as "लग रहा", "शायद", "likely" or "suspected". "Impression …" alone is not a hedge. Telugu and Tamil hedges aren't listed yet. |
| C-44 | In `typed-local-2` `fam-005-a` the model called the doctor's "Telma forty दिन में एक बार…" patient speech, and Check 1 dropped the medicine with only a warning, so it vanished from the report and its expected `missing_quantity` never fired. | Test-first: a medicine called patient speech is dropped only on evidence, a `[patient]` line label or, unlabelled, a first-person sentence. Otherwise it is kept and blocked `speaker_unclear` for the doctor to confirm. |
| C-45 | Rerunning the pipeline on a case deleted every file in its folder, including the doctor's approval, signed PDF, FHIR bundles and earlier draft versions. It happened on 2 Nov: a cache rebuild erased `fam-008-a`'s approval. Found by the branch review. | Test-first: those files move aside (D-90) before the rerun clears the folder. |
| C-46 | Approving again, for example after a further correction, overwrote the earlier approved record, PDF and bundles in place. Found by the branch review. | Test-first: a different approval moves the earlier signed files aside (D-90). |
| C-47 | A blocking `omission` could never be cleared, so a draft whose stage 2 left a finding out could never be approved (11 such blocks in `typed-local-2`). Found by the branch review. | Test-first: `add_line` and `dismiss_item` (D-89). |
| C-48 | The schedule parser treated any " not " as a self-correction, so "when needed, not more than four times a day" lost its daily maximum with no flag. It treated any "नहीं," the same way, so "…से ज़्यादा नहीं, खाने के बाद" lost its timing. Found by the branch review. | Test-first: only a trailing ", not <number>" or a standalone ", नहीं," is a correction, and "not more than" sets the maximum. Real corrections still keep only the new value. |
| C-49 | The prescription FHIR bundle carried every resource from the consultation (Observations, Conditions, allergies, orders, statements) though its Composition references none of them. Found by the branch review. | Test-first: it now holds only the patient, doctor, clinic, encounter and medicine requests. |
| C-50 | The patient box printed "5 डॉक्टर से पूछें" for a unit missing from its template (ml, mg), and a bare "डॉक्टर से पूछें" line for each unresolved medicine without saying which. Found by the branch review. | Test-first: an unlisted unit prints as itself, and an unresolved row names the medicine from its verified quote. |
| C-51 | The approved PDF printed the approval time in UTC ("14:43 UTC" for 20:13 in India), and a refused correction left a stray `report.next.pdf`. Found by the branch review. | Test-first: times print in IST; the archive check now runs before anything is rendered. |
| C-52 | `fam-011-v3` on Groq: the name quote was only "Amlong" (resolves to 5 mg) while the spoken name "Amlong two point five" resolves to 2.5 mg, so the grounding rule (D-77) blocked a correct medicine. The J-22 fallback could also have let a short quote pick one strength exactly. | Test-first: a spoken name found verbatim in the transcript is grounded and its exact match stands; the J-22 fallback may only make a medicine ambiguous, never exact. The "strength changed" sabotage still blocks. |
| C-53 | The scorer paired medicines on the name quote alone, so a brand-only quote ("Wysolone") failed to pair with evidence "Wysolone ten". Three cases counted their medicines as missing and extra: Groq showed 26 of 33 exact and 6 extra when the truth was 31 and 0. | Test-first: typed pairing uses the quote and the spoken name together. Scoring only; the pipeline was right. |
| C-54 | A taper's food rule ("सुबह खाने के बाद" in every step) is said inside the taper phrase, which the prompt keeps whole in the timing field, so food stayed empty in `fam-010`. | Test-first: when a taper has no food phrase, its single food rule is read from its own verified timing phrase. |
| C-55 | The first embedding run stopped on duplicate chunk ids. NLEM ids were built from the ingredient key, so "Betamethasone" and "Betamethasone dipropionate" collided; and three medicines listed in two sections with different marks or capitals ("Doxycycline" and "Doxycycline** #", "Sodium Valproate" and "Sodium valproate") were kept twice. | Test-first: ids use the medicine's full name, and listings of one medicine merge after footnote marks and capitals are set aside. NLEM now gives 378 medicines (was 381) and 32,477 chunks in all, every id unique. |
| C-56 | GPU embedding didn't start. A separate environment, `.venv-embed` in the root folder (fastembed-gpu 0.9.1, 798 MB), reusing Whisper's CUDA 12 cuBLAS and cuDNN, fell back to the CPU each time: onnxruntime-gpu 1.31.1 and 1.27.0 both import `cublasLt64_13.dll` and `cufft64_12.dll`, i.e. CUDA 13, although 1.27.0's package metadata names CUDA 12 libraries. The CPU and GPU-environment vectors matched (cosine 1.0 on 8 chunks). | Not fixed yet. CUDA 13's libraries are about 1.1 GB to download, so Aditya is asked first. The CPU run continues meanwhile. |
| C-57 | Fixes C-56. Aditya approved the CUDA 13 download. | Installed `onnxruntime-gpu[cuda,cudnn]==1.31.1` (cuBLAS 13.8, cuDNN 9.27 for CUDA 13, cuFFT, cuRAND) into `.venv-embed`, now 1,966 MB, and removed the CUDA 12 extras added in C-56. The RTX 5060 runs the model: 32,546 chunks in 3 minutes 12 seconds, against about 3.5 hours on the CPU, with vectors matching the CPU's (cosine 1.0 on 16 chunks). `embed_chunks.py --gpu` stops with an error if onnxruntime falls back to the CPU. The CPU run was stopped at about a third. |
| C-58 | Two retrieval bugs found while testing questions. Chunk ids were read back by splitting on spaces, but Jan Aushadhi ids contain spaces ("Central Nervous System (CNS)"), so every Jan Aushadhi hit pointed at the wrong chunk. And only the first part of a long Jan Aushadhi group carried its heading, so "generic for diabetes" missed the Anti-Diabetic group. | Test-first: ids are read one per line; every Jan Aushadhi part repeats its group heading and stays under 800 characters (179 chunks, was 110). Anti-Diabetic now ranks 4th for that question, behind small groups whose names share the query's words. The group names don't say "diabetes", so keyword search in Postgres (which stems "diabetic" and "diabetes" alike) should be combined with vector search. |
| C-59 | The brand lookup returned "Telma 40" with no composition. In 239,220 of the 246,068 current products the dataset's `salt_composition` is empty; the composition is only in `short_composition1` and `short_composition2`. So the list of ingredients sold in India came from 6,848 products, and both the label selection and `indian_products` missed most medicines. | Test-first: `product_composition` uses `salt_composition` when it is filled, else joins the two short columns (which hold at most two ingredients). Ingredients sold in India: 1,639 (was 945). Labels kept: 1,881 (was 1,322); 46,540 chunks in all. 884 of the 1,639 ingredients have a US label of their own, covering 72% of ingredient mentions; the most common without one are aceclofenac, domperidone, methylcobalamin, ambroxol, nimesulide, ornidazole, thiocolchicoside and etoricoxib (India-only), plus clavulanic acid, sulbactam and tazobactam (US labels only in combinations). Earlier figures (D-96, the 945 and 570 counts) were built on the 6,848. |
| C-60 | Search in Supabase, tested on 10 questions, needed five fixes. (1) Supabase refused `hnsw.*` settings in the function definition, so they are set per call. (2) The vector index found only 7 of the true 10 nearest chunks for "domperidone uses" at pgvector's default width (40), 9 at 100 and 10 at 400; it now uses 400. (3) Postgres ranks text without weighing rare words, so "use" and "side" pulled unrelated chunks up; a list of words in over 2% of chunks fixed that but also dropped "diabetes". Each query word now weighs log(chunks / chunks holding it), from a `knowledge_words` table filled at each load, and words in a fifth of chunks or more are skipped. (4) Hundreds of chunks tie on "telmisartan" alone, and arbitrary ranks among the tied chunks outweighed the best vector match; tied chunks now share a rank, and keyword-only results join only from the top three ranks. (5) The index build ran the free plan out of shared memory; it now runs on one worker with 64 MB. A failed upload rolls back whole, so the old data stays. | Results after the fixes are under Verification. Added an ingredient filter to `match_chunks` for brand questions. |
| C-61 | In the live Gnani check (3 Nov), Timbre's WAV came back as a stream: the RIFF and data sizes in its header were left at 0xFFFFFFFF. Read as written, the clip claimed hours of audio, so the 30-second check refused the synthetic voice note with HTTP 422 after the Timbre call had already been spent. The fake client had always returned a correct header, so the tests missed it. | `agent/voice.py` now sets both sizes from the bytes actually present (`repair_wav_sizes`) before the length check and before caching, so Prisma and the browser get a correct file too. Regression tests use a streaming-header WAV. The retry reused the cached Timbre audio, so the fix cost one Prisma call and no extra Timbre call. |
| C-62 | On Devansh's Windows laptop (4 Nov) two tests in `test_followup_visits.py` failed with `UnicodeDecodeError: 'charmap'`: they read and wrote JSON fixtures with `read_text()`/`write_text()` and no encoding, so Windows used cp1252 on UTF-8 Hindi text. The suite had only run on Linux, where the default is UTF-8. | The test file now passes `encoding="utf-8"` everywhere. The suite passes on Windows without `PYTHONUTF8=1`. |

## What was done

All on 2 Nov 2026.

| Step | Result |
|---|---|
| Reviewed the idea | Read all five planning files, including the architecture page embedded in its HTML. Checked them against the challenge page and Gnani's docs. |
| Listed what's needed before starting | Access, people, decisions, and contradictions between the docs. Found the Diwali clash and the missing test harness that the roadmap refers to. |
| Checked free model options | Gemini Flash free tier as first choice, with Groq's open-weight Qwen to compare. |
| Created the repo tree | Commit `4d3d3fe` on `main`. |
| Read Gnani's rules | The challenge page, participation terms and EULA. Found the benchmark clause. |
| Reviewed dataset options | Checked licences and sources. Conclusion: build our own. |
| Fact-checked ASTRA's review | Its facts held. Adopted the method, changed the numbers, and added the gaps below. |
| Updated the data method | Commit `c8e7af0`. |
| Downloaded data | 7 datasets, checked and recorded. Commit `1096ce8`. |
| Built the first 12 families | Cases, seed, formulary, checker and tests. Commit `91bd421`. |
| Researched free audio | See below. |
| Wrote this runbook | Commit `7a7cdac`. |
| Set up free audio | Stored the Gemini key, installed faster-whisper and the GPU libraries, downloaded Whisper large-v3, and ran one clip through both. |
| Rendered and transcribed | Built `render_audio.py` and `transcribe_audio.py` test-first. 22 clips rendered and transcribed. Found and fixed Whisper's silent truncation. |
| Designed extraction and report | Agreed the design with Aditya in four steps, and wrote the spec. |
| Planned extraction and report | Aditya approved the spec. Wrote [the plan](docs/superpowers/plans/2026-11-02-extraction-and-report.md): 17 tasks, each test-first, with expected values taken from the case files. |
| Switched to Mistral | Mistral first, Gemini as fallback, behind one model client. Spec and plan updated. See D-59. |
| Checked ASTRA's plan review | All six main points held, and so did both smaller corrections. Only its advice to keep two Gemini stages was out of date. Revised the spec and plan, adding Task 10b (doctor corrections) and Task 14b (cached end-to-end and sabotage tests), 19 tasks in all. |
| Dropped Mistral, added a local model | Mistral's key was rejected. Pulled `qwen3:8b` into Ollama, moved its models to the root folder, and probed it on two typed scripts. Rewrote Task 4 for a Gemini and Ollama client, and added a local comparison run to Task 16. See D-70. |
| Handed the build to ASTRA | Added "Handoff to ASTRA" to the plan: what to read, the setup, the working rules, and the note to leave when finished. Moved the key-leak check into `tools/key_leak_check.py` so it can run without Claude. See D-71. |
| Added Groq | Stored the key in `.env`, compared two Groq models, and added an OpenAI-compatible adapter test-first (6 tests). The fallback order is now Gemini, Groq, local. See D-85 and J-20. |
| Finished Task 16 and the branch review | Scored Groq and the local model on typed scripts and Whisper text; corrected and approved `fam-008-a` end to end; reviewed the whole branch (9 findings) and fixed all of them plus 3 found while re-scoring (C-45 to C-54, D-88 to D-90). 372 tests pass. |
| Ran the Prisma 5-clip trial | Aditya asked to test Prisma keyterms first. Transcribed `fam-001-a`, `fam-005-a`, `fam-006-a`, `fam-007-a` and `fam-008-a` with and without the 26 formulary brand names as keyterms (10 requests), ran both sets through the Groq pipeline, and scored them. The runner and scorer now take `prisma` and `prisma-keyterms` as sources. See D-91 to D-93; results are in the private note `../prisma-trial-2026-11-02.md`. |
| Built the medicine knowledge chunks | Downloaded openFDA's label export (14 files, 262,903 labels), and wrote `tools/knowledge/` test-first: a name map, label selection and chunking, an NLEM 2022 parser and a Jan Aushadhi grouper (25 tests). The build gives 1,322 labels as 31,989 chunks, 381 NLEM medicines and 110 Jan Aushadhi groups. Read samples from each source and fixed what they showed: brand names in titles, NLEM table headers and notes inside categories, and form words inside Jan Aushadhi ingredients. See D-94 to D-99. |
| Built a code knowledge graph | Ran `graphify update .` on the repo: 725 nodes, 1,742 edges, 35 communities, from code only with no model calls. Output is in the git-ignored `graphify-out/`. Query it with `graphify query "<question>" --budget 600` before reading whole files. |
| Implemented extraction/report tasks 0–15 | Contracts, references, number/schedule parsing, medicine matching, both model stages and checks, frozen drafts, audited corrections, approval, patient-language templates, PDFs, FHIR, runner, sabotage fixtures and scorer. 332 tests pass; Task 16 is in progress. See build log below for per-task checkpoints and D-72 onwards for deviations. |
| Researched and built the follow-up agent demo, 2–3 Nov | Research with Serper (51 searches, 39 pages; [summary](docs/research/followup-agent.md)) and a [design](docs/superpowers/specs/2026-11-02-followup-agent-design.md). Merged `aditya/extraction-report` into the session branch (J-23). Built test-first: contracts, plan, red flags, routing, grounded answers, gate, conversation engine, two new offline fixtures (`fam-004-a`, `fam-010-a`), the API and the Next.js chat page. Seed patients gained `followup_whatsapp` consent. 438 tests pass; the browser check passes 18 of 18 on desktop and phone widths. |
| Added voice notes and approval-started follow-up, 3 Nov | Read Gnani's docs for the Prisma and Timbre REST endpoints. Built test-first: the Gnani client, voice in the conversation, approved-visit scanning, `voicerx.approve --review-date --followup`, the voice and visit API endpoints, and the web page's Listen, 🎤 and 🔊 controls (D-111, D-112). No live Gnani call yet: this container has no `GNANI_API_KEY`. 471 tests pass; the browser check passes 24 of 24 with the fake speech client and 20 of 20 with voice off. |
| Live Gnani voice check, 3 Nov | Devansh supplied a Gnani key for this session; it was kept in the ignored `.env` only. A scratch script drove the real API (`create_app` with a counting transport) through 4 calls: Timbre on the Hindi and English visit summaries, Timbre for a synthetic patient voice note, and Prisma on it. Found and fixed C-61 (474 tests pass, 2 skipped). Sent the three clips to Devansh to listen to. Prisma output is not recorded here (Q-04). |
| Added real WhatsApp for private testing, 3 Nov | Read Meta's Cloud API docs (messages, reply buttons, audio, media, webhooks, signatures). Built test-first: `agent/whatsapp.py`, the webhook and tunnel guard in `app.py`, Ogg voice notes to Prisma, and WhatsApp mode in the web page. Wrote `docs/whatsapp-testing.md` (D-113). No Meta account is reachable from the cloud container, so the first real run is Devansh's on his laptop. |
| Added WhatsApp voice calls, 3 Nov | Read Meta's Calling docs (overview, user-initiated calls, sandbox, pricing, call settings). Built test-first: the call loop and VAD (`agent/call.py`), the aiortc media (`agent/webrtc_call.py`), call handling in `app.py`, `enable-calling`, and call wording in the templates (draft, pending review). Added `aiortc==1.15.0` to the API requirements (D-114). |

Gaps added to ASTRA's review: the keyterm leak, the EULA, credit cost, reserved voices, and the conflict between its Synthea advice and its own rule on histories.

## What exists

| Item | Where | Notes |
|---|---|---|
| 12 case families, 25 scripts | `data/eval/cases/`, `data/eval/scripts/` | 7 Hinglish, 2 English, 1 each Hindi, Tamil, Telugu |
| 29 patient questions | Inside the case files | 14 answer, 13 escalate, 2 urgent |
| Split and manifest | `data/eval/splits.json`, `data/eval/manifest.csv` | All development |
| Seed records | `data/seed/` | 1 clinic, 3 doctors, 30 patients |
| Starter formulary | `data/formulary/products.csv` | 25 rows, unverified |
| Checker and tests | `tools/corpus/` | 97 tests |
| Download record | `data/DOWNLOADS.md` | Versions, licences, checksums |
| Data rules and method | `data/README.md` | |
| Extraction and report backend | `services/api/voicerx/` | CLI workflow; no review screen yet |
| Report evaluation | `tools/eval/score_report.py` | Typed metrics, and approximate ones for Whisper and Prisma text; explicit incomplete/missing coverage |
| Medicine knowledge chunker | `tools/knowledge/` | `download_openfda_labels.py`, then `build_chunks.py`; output in `../DATA/knowledge/chunks/` (D-98) |
| Prisma transcription | `tools/corpus/transcribe_prisma.py` | Prisma v3.0 REST, optional formulary keyterms; output is git-ignored (D-91) |
| Local run artifacts and response cache | `runs/` | Ignored by git; synthetic inputs only |
| Follow-up agent | `services/api/voicerx/agent/`, `services/api/voicerx/contracts/followup.py` | Plan, red flags, routing, grounding, gate; Hindi and English wording in `agent/templates/` |
| Follow-up demo API | `services/api/voicerx/app.py` | FastAPI; conversations saved in ignored `runs/followup-demo/` |
| Follow-up chat demo | `apps/web` | Next.js 16; `scripts/e2e.mjs` browser check |
| Warning-sign rules | `data/rules/red_flags.yaml` | Draft, Hindi (Devanagari and Latin) and English, pending doctor review |
| Offline demo fixtures | `services/api/tests/fixtures/fam-004-a`, `fam-010-a` | Hand-written stage outputs quoting the typed scripts; both pass Check 1 and 2 |
| Gnani speech client | `services/api/voicerx/ingest/gnani.py` | Prisma v3.0 and Timbre v3.0 REST; `fake_speech.py` beside it for tests |
| Follow-up voice and visits | `services/api/voicerx/agent/voice.py`, `agent/visits.py` | On-demand voicing with cache, voice-note transcription, approved-visit scan, `start_followup` |
| Real WhatsApp channel | `services/api/voicerx/agent/whatsapp.py`, `docs/whatsapp-testing.md` | Cloud API client, webhook parsing and signature check, delivery with the 24-hour window, phone numbers in memory only. Off unless the `WHATSAPP_` settings are in `.env` |
| WhatsApp calls | `services/api/voicerx/agent/call.py`, `agent/webrtc_call.py` | Half-duplex call loop with VAD, Prisma per turn and Timbre replies; aiortc WebRTC answerer for Meta's Calling API |
| Settings template | `.env.example` | Every setting the code reads, with empty values; now includes the five `WHATSAPP_` settings. Copy it to `.env` (git-ignored) |

Known coverage gaps: no two-person consultations, no held-out cases, 2 orthopaedic families, 1 family each for Hindi, Tamil and Telugu, and the shortest scripts are under the 15-second target by estimate.

## Verification

| Check | Result |
|---|---|
| Unit tests | 97 pass |
| Checker on the 12 families | Passes |
| Deliberate errors in real cases | 13 of 13 caught |
| Invented number per family, in every language | 12 of 12 caught |
| Invented medicine per family | 12 of 12 caught |
| Checker rules disabled one at a time | 23 of 23 caught |
| Download checksums | 10 of 10 match |
| Sensitive-content scan of pushed files | Clean |
| Gemini key | Accepted, HTTP 200 |
| Whisper `model.bin` against Hugging Face's checksum | Matches |
| One clip, script to Gemini audio to Whisper text | Works. Every fact survived, including "बुखार नहीं है". |
| Whisper speed on the 21.9-second clip | GPU 8.0 seconds (2.7× real time), CPU 80.1 seconds (0.3×) |
| Python dependency check | No broken requirements |
| Clips rendered | 22 of 25: 11 from `gemini-3.8-flash-tts`, 11 from `gemini-3.8-flash-lite-tts` |
| Whisper on the 22 clips, after the chunking fix | 0 truncated, 1,223 of 1,250 script words, every clip within 10% of its script |
| Unit tests | 128 pass |
| Mistral key | Rejected, HTTP 401 "Invalid API Key" |
| `qwen3:8b` on `fam-001-a` and `fam-008-a`, forced JSON schema | 26 of 26 quoted phrases exact. Missed one negation. Fully on the GPU at 8,192 tokens of context, 16.5 tokens a second. |
| Ollama model folder | The server log shows `D:\Study\JANANI\models\ollama`, and `ollama list` shows both models |
| First Groq typed run (`typed-groq-1`, `extract-v2`, `report-v1`) | 25 of 25 drafts. Facts found 157/173, false facts 17/174, negation 153/157, sides 157/157, medicines exact 20/33, expected flags 7/7, sections 139/157, unsupported lines 0/174, unexpected blocks 20 (explained in C-36, C-37, C-39). Superseded by the rerun on `extract-v3`. |
| Second Groq typed run (`typed-groq-2`, `extract-v3`, `report-v2`), first 15 cases before the daily limit | 15 drafts, 10 incomplete (C-42). Facts found 96/112, negation 96/96, sides 96/96, medicines exact 16/16, expected flags 5/5, unsupported lines 0/115, unexpected blocks 3: one fixed in C-40, two judged in J-21. |
| `fam-008-a` corrected and approved end to end (`typed-groq-2`) | Rebuilt from cached replies with C-43: 3 blocks. Corrections: chose Pan 40, removed Mucaine gel, edited "acid reflux" to "Suspected acid reflux". Version 2 with 0 blocks, `draft_report.v1.json` kept, approval wrote `report_approved.pdf` (no watermark, footer shows version 2 and approver) and both FHIR bundles. Open: the prescription bundle also carries the consultation's Observation, and the approval time prints in UTC. |
| Typed runs on `extract-v3` and `report-v2`, after C-36 to C-44 and J-22 (drafts rebuilt from cached replies) | Groq `gpt-oss-120b`, 16 of 25 (9 wait on the daily limit): facts found 102/118, false facts 19/121, negation 102/102, sides 102/102, medicines exact 18/18, extra medicines 0, expected flags 6/6, sections 87/102, omissions 0, duplications 0, unsupported lines 0/121, unexpected blocks 4. Local `qwen3:8b`, 25 of 25: facts found 148/173, false facts 52/200, negation 147/148, sides 144/148, medicines exact 20/33, extra medicines 12, expected flags 8/8, sections 102/148, omissions 11, duplications 55, unsupported lines 0/244, unexpected blocks 97. |
| What the unexpected blocks are | Groq: 2 invented-side quotes (J-21) and 2 hedged diagnoses recorded as stated (C-43). Local: 54 certainty (49 "Provisional:" written on stated items, 5 hedges), 11 omissions, 10 non-verbatim medicine phrases, 10 invented sides, 5 negation, 3 missing quantity, 2 speaker unclear, 1 unmatched, 1 subject. Every one checked by case: each is a model error the checks rightly blocked, none a check defect. |
| Conclusion | Both models: every expected flag fires and no unsupported line reaches a report. Groq is the working model: near-perfect on the cases it ran. The local model is safe, because its errors are blocked, but too noisy for a doctor: about 4 blocks a report, and a duplicated line in most. |
| Final typed runs, all fixes to C-54 (`typed-groq-2`, `typed-local-2`, `extract-v3`, `report-v2`) | Groq, 25 of 25: facts found 154/173, false facts 20/174, negation 152/154, sides 153/154, medicines exact 33/33, extra 0, expected flags 8/8, sections 133/154, omissions 0, duplications 0, unsupported lines 0/174, unexpected blocks 8 (model errors caught: 2 side-less quotes, 2 hedges, 3 negations, 1 quote spanning two clauses). Local, 25 of 25: facts 148/173, false facts 52/200, medicines exact 21/33, expected flags 8/8, unsupported lines 0/244, unexpected blocks 98, duplications 55. |
| Whisper runs (22 transcripts; 3 `missing_input`) | Groq (`whisper-groq-1`): 21 drafts, 1 incomplete (invalid JSON twice, no report written), facts found 121/147, false facts 24/145, negation 121/121, sides 120/121, medicines exact 5/26, expected flags 5/6, unsupported lines 0/144. Local (`whisper-local-1`): facts 69/154, medicines exact 3/29, expected flags 5/6. Scores on Whisper text are approximate (its spelling differs from the scripts). |
| Why Whisper medicines score low | Whisper writes brand names in Devanagari ("डोलो 650", "टेलमा 40", "पैन"): 16 of 23 Groq medicines and 19 of 27 local ones. The matcher knows only Latin spellings, so each is `unmatched` and blocked, as the plan's Review Focus 5 requires. Safe, but the audio path cannot resolve most medicines yet. The one missed expected flag (`fam-008-a` `ambiguous_product`) is the same cause: "पैन" came back unmatched, still blocked. See Q-20. |
| Extraction/report and corpus full suite | 332 pass, including all ten planned end-to-end sabotages and additional evidence/approval regressions |
| Live `fam-001-a` PDF layout | One A4 page; Hindi shaped, four medicine slot columns, draft watermark, review block and page-margin footer visually checked |
| Prisma 5-clip trial, with and without keyterms (`prisma-groq-1`, `prisma-keyterms-groq-1`) | 10 of 10 requests HTTP 200; 10 of 10 drafts. Accuracy is recorded only in the private note (Q-04). Safety finding, D-92: with keyterms, one ambiguous medicine became a specific product with no block. |
| Medicine knowledge chunks | 25 tests pass. openFDA download: 14 of 14 files, checksums in its manifest. Of 945 ingredients sold in India, 570 have a US label of their own, covering 69% of ingredient mentions across Indian products. The rest are mostly India-only medicines (methylcobalamin, ornidazole, domperidone, acebrophylline) or appear in the US only in combinations. NLEM: 381 medicines parsed, against about 384 listed. |
| Local retrieval on 11 sample questions (bge-base, `search_local.py`) | Right sources at the top for medicine questions: "what is telmisartan used for" (Telmisartan, Uses, 0.854), "paracetamol overdose liver damage" (acetaminophen Overdose sections; the name map isn't needed at query time), "dose of amoxicillin clavulanate for children" (its Dosage and Children sections), "azithromycin in pregnancy", "can I take ibuprofen with telmisartan" (Telmisartan, Interactions), "medicines for high blood pressure in India essential list" (NLEM antihypertensives). "Domperidone uses" finds its NLEM entry first (0.733), then unrelated labels near 0.70, since it has no US label: answers need a score floor. Weak: Jan Aushadhi groups (C-58), and near-identical OTC acetaminophen combinations crowd the top results, so results should be spread across labels. |
| Supabase upload, 3 Nov (`upload_supabase.py`) | `knowledge_chunks` 46,540 rows (308 MB with indexes), `indian_products` 246,068 rows (59 MB), `knowledge_words` for keyword weights. Database 382 MB of the free plan's 500 MB. Upload about 90 seconds, index build about 2 minutes. Rerun-safe: each run replaces the contents in one transaction. |
| Supabase search after C-60 (`search_supabase.py`, `match_chunks`) | "what is telmisartan used for": Telmisartan Uses first (0.854). "can I take ibuprofen with telmisartan": Telmisartan Interactions first. "domperidone uses": its NLEM entry first (no US label exists). "Jan Aushadhi generic for diabetes": Anti-Diabetic first. "paracetamol overdose liver damage": six acetaminophen Overdose sections. "azithromycin in pregnancy": azithromycin Pregnancy sections. Brand: "Telma 40" resolves to telmisartan, then its side effects and pregnancy sections; "Dolo 650" to acetaminophen, then dosing. Weak: a brand's search returns combination products as well as the single medicine, and ignores the route ("Dolo 650 maximum dose" puts intravenous acetaminophen dosing first). |
| Supabase database connection, 3 Nov | Session pooler (`aws-1-eu-central-1`, port 5432) with psycopg 3.3.6: connected to PostgreSQL 17.11. The connection string kept the template's square brackets around the password, and the password holds an `@`; the copy in `.env` (`SUPABASE_DB_URL`) drops the brackets and URL-encodes the password, and Aditya's file is unchanged. pgvector 0.8.2 turned on in the `extensions` schema, with `halfvec` available. No tables yet; database 10 MB. Password leak check on the repo and its history: clean. |
| Supabase connection, 3 Nov | Project `rftuxwsnfinuygewssas`. Auth health with the publishable key: HTTP 200. Schema listing with the publishable key: refused (401, "Secret API key required"), as intended. Schema listing with the secret key: HTTP 200, no tables yet. Whether pgvector is on can't be seen through the API. Leak check on both keys: clean. |
| Unit tests after the Prisma source was added | Runner and scorer suites pass, including a new test that each speech source reads its own folder |
| Full suite after the follow-up agent, cloud container, 3 Nov | 438 passed, 2 skipped (`PDF_BROWSER=tools/cloud/headless-chrome.sh`) |
| Follow-up agent sabotage tests | A changed dose, an uncited answer, a softened urgent reply, a non-urgent reply to a warning sign, an altered report and a check-in outside sending hours are all refused by the gate |
| Follow-up patient questions (`tools/eval/followup_questions.py`) | 7 of 7 expected actions (answer 3/3, escalate 3/3, urgent 1/1), 0 forbidden claims. Coverage 7 of 29 questions; development data, not held out |
| Follow-up browser check (`apps/web/scripts/e2e.mjs`) | 18 of 18 on 1280 px and 390 px widths: AI disclosure and approved medicine in the summary, quick replies, worse and urgent tasks, STOP, grounded answer, stop-medicine request escalated, no horizontal scroll |
| Full suite after voice notes and approval-started follow-up, 3 Nov | 471 passed, 2 skipped. Voice tests run on a fake Gnani client: request shape, 429 retry, key never in errors, cache, WAV limits, empty transcript, voice red flag, no stored recording. |
| Browser check with voice, 3 Nov | 24 of 24 with `VOICERX_FAKE_SPEECH=1` (Listen, synthetic voice note answered from the approved row, fake-microphone recording converted to WAV and accepted) and 20 of 20 with voice off (controls disabled with the reason). No live Gnani call has been made for the follow-up yet. |
| Live Gnani voice check, 3 Nov | Worked: Timbre on the `fam-010-a` Hindi summary (HTTP 200, valid mp3), Timbre on the `fam-004-a` English summary (HTTP 200, valid mp3), Timbre synthetic patient note (HTTP 200, 16 kHz 16-bit WAV after C-61), Prisma on that note (HTTP 200, transcript returned and routed by the normal rules), and replays served from the cache with no call. Failed first: the synthetic note, refused by our own length check (C-61), fixed and retried once. 4 Gnani calls in all (3 Timbre, 1 Prisma), no 429. Transcript text and accuracy are not recorded here (Q-04); latency was not measured. |
| WhatsApp channel against a fake Graph API, 3 Nov | 21 tests in `test_whatsapp.py`: webhook verification and signatures, the allowlist, JOIN and help, reply buttons and button taps, red flag, medicine answer, Meta retries, Ogg voice note to Prisma and a voice reply, the 30-second limit, the 24-hour window, waiting after a restart, the tunnel guard, and no phone number in any stored file or log. Full suite 495 passed, 2 skipped. A local run with the API pointed at a Graph stub: a signed `JOIN fam-010-a` delivered the summary, a typed MONTAIR question got the approved row, Advance from the web page sent the check-in as three reply buttons, and a request through the tunnel to `/visits` got 403. Browser check 24 of 24 (fake voice). Not yet run against Meta. |
| WhatsApp calls in the container, 3 Nov | 11 tests in `test_call.py`: VAD (cut at silence, clicks ignored, 25-second cap); greeting first; a medicine answer from the approved row; red flag, DOCTOR and STOP end the call; two silences; the turn cap; hang-up; replies cached; the caller's audio in no file. In `test_whatsapp.py`, an in-process WebRTC loopback: a second aiortc peer sent an Opus offer through a signed `connect` webhook, got our answer from `pre_accept`, and connected. The agent sent `accept`, greeted, heard the caller's tone burst, transcribed it (fake client), and spoke the MONTAIR answer, which also went to the chat. Repeated 3 times, all passed. Unknown and unbound callers get `reject`. Full suite 539 passed, 1 skipped; the PyAV audio-render test now runs because aiortc installs PyAV. Not yet run against Meta. |

What the checker can't do: it confirms that quotes exist and that scripts and specs agree. It can't tell whether a quote truly means the fact, or whether a case is clinically right. Those need people.

## Open questions

| ID | Question | Owner |
|---|---|---|
| Q-01 | Are both members registered and eligible, and who is the primary registrant? | Team |
| Q-02 | Is the Gnani key limited to one active request? If so, a live call can't hold speech-to-text open while speaking. | Team, once the key exists |
| Q-03 | What does a Gnani credit buy? No published rate was found. | Team, using a small test |
| Q-04 | May entries publish Prisma accuracy results? The EULA restricts this. Until answered, none go public. | Ask on Gnani Discord |
| Q-05 | May PriMock57 be used, given it is recorded mock consultations? | Ask on Gnani Discord |
| Q-06 | Who are Builder A and Builder B? | Team |
| Q-07 | Is the product VoiceRx or JANANI? The package is `voicerx` for now. | Team |
| Q-08 | Which doctor reviews, and when? | Team |
| Q-09 | Who reads Telugu and Tamil? | Team |
| Q-10 | How does Timbre read mixed Devanagari and Latin text? | Partly answered: the `fam-010-a` Hindi summary (with `language: auto`) was rendered live on 3 Nov and sent to Devansh. Nobody has listened yet. |
| Q-11 | Should D-30 to D-36 go ahead? | Team |
| Q-12 | The roadmap's test harness, `test-results.json` and JSON schemas aren't in any folder. Does anyone have them? | Team |
| Q-13 | What are the Gemini free-tier limits for speech? Google doesn't publish them in its docs. | Check AI Studio, or find out while rendering |
| Q-14 | How well does Gemini read Hinglish, Tamil, Telugu and cross-talk? Only one Hinglish clip has been made, and nobody has listened to it yet. | Team, by listening |
| Q-15 | Gemini's terms bar use "in clinical practice, to provide medical advice". Which model would a real product use? | Team, before any real deployment |
| Q-16 | Do the two Gemini keys share one project's daily limit? One request would tell. | Assistant, when it is needed |
| Q-18 | Is Mistral's free Experiment plan activated on the account? Until it is, Mistral allows no chat requests. | Closed: the key is invalid and Mistral is dropped. See C-29. |
| Q-17 | Whisper's Tamil is weak. It produced invented words such as "testosterone" and stray Cyrillic and Korean characters, which changed between runs. Should Tamil be scored only on typed scripts? | Team |
| Q-19 | Do doctors often dictate in the first person ("I'll start Telma")? If so, D-63 will block too many medicines and needs a narrower rule. | Doctor reviewer, and the first typed run |
| Q-20 | How should medicine names spoken in Indian script be resolved? Whisper writes most brands in Devanagari, so they never match the Latin formulary. Options: add Devanagari, Telugu and Tamil spellings to each formulary row as aliases (exact, auditable), transliterate before matching (any match would stay fuzzy, so blocked), or rely on Gnani Prisma's keyterm boosting to output Latin brand names (test in the planned 5-clip Prisma trial). | Closed: Prisma `codemix` without keyterms writes brands in Latin (D-93); keyterms are off (D-92). |
| Q-21 | Should phrase binding ignore the nukta? In the trial the model quoted "ज़रूरत" where Prisma wrote "जरूरत", so a stated timing failed to bind and was blocked. Folding ज़/ज, फ़/फ and the like would bind it, at the cost of a slightly looser verbatim rule. | Team |
| Q-22 | Should a medicine with no timing or duration be flagged when the transcript states one? Twice in the trial the model left out a stated timing or duration, and the report showed it as not stated with no flag. The doctor sees "not stated", but nothing points at the omission. | Team |
| Q-23 | What should the medicine knowledge do first: look up any Indian brand, warn the doctor (a medicine that doesn't fit the diagnosis, a dose out of range, an interaction), or answer patients' medicine questions with citations? | Aditya |
| Q-24 | Which embedding model and vector database? The suggestion is Chroma on this machine with a free open model; both are new downloads. | Closed: Supabase (D-100) and bge-base-en-v1.5 (D-101). |
| Q-25 | Can the approval screen capture a structured review date, so review reminders never depend on model-written text? | Partly answered: `voicerx.approve --review-date` records it (D-112). The web approval screen doesn't exist yet. |
| Q-26 | Which doctor reviews the red-flag list and the follow-up templates, and when? Telugu and Tamil follow-up templates and warning signs are not written yet. | Team |
| Q-27 | Does the demo need outbound calls at all, given business-initiated WhatsApp calling isn't listed for India? | Team Note (3 Nov): business-initiated WhatsApp calls aren't available from US numbers, which includes Meta's test number; patient-initiated calls are built (D-114). |
| Q-28 | How many Prisma and Timbre credits may the follow-up demo use for voice notes? | Partly answered: on demand and cached, about 5 live calls to verify (D-111). A budget for the final demo is still open. The live check on 3 Nov used 4 calls. |
| Q-29 | When a patient's voice note names an approved medicine in a spelling that doesn't match the approved brand exactly, the question goes to the doctor rather than being answered (safe, and D-92 rules out sending brand keyterms to Prisma). Should the agent instead ask the patient to pick from the visit's approved medicines with buttons, so the answer still comes only from an approved row? | Team |
| Q-30 | Should the bot ever send text a model wrote, for example small talk or a plain-language explanation of an approved instruction? Today (D-115) it never does: the model only classifies, and every reply is fixed template text. Allowing it would need a checker like Check 2 for every sentence. | Team |

## Free audio research

**Question:** can we get audio without spending Gnani credits before the pipeline is proven?

**Finding:** yes, for development. Two separate costs have to be replaced: making audio, and transcribing it. No published Gnani credit rate was found, so the real cost is unknown until a small test runs.

Proposed order (D-36):

1. **No audio.** Run typed scripts through extraction, using free LLMs. This tests most of the pipeline at no cost.
2. **Free audio, free transcription.** Render scripts with Gemini TTS, and transcribe them with Whisper on the local GPU. This tests the audio path.
3. **A small Gnani test.** Run about 5 clips to measure credit use and how Prisma handles real clips.
4. **Gnani for what must be Gnani.** Final evals, keyterm tests and the demo.

Making audio:

| Option | Licence or cost | Languages | Notes |
|---|---|---|---|
| Gemini 3.8 Flash TTS | Listed free tier | Hindi, Tamil, Telugu, English | Up to 2 speakers per request, and 16 kHz is available. Mixed-language handling isn't documented. Free-tier inputs may be used by Google, so synthetic text only. **First choice.** |
| Synthetic Medical Dictation dataset | CC BY 4.0, 1.8 GB | US and UK English only | Ready-made audio, fully synthetic. Good for a first plumbing test. |
| Indic Parler-TTS | Apache 2.0, gated | Includes Hindi, needs checking for Tamil and Telugu | Needs a Hugging Face account. Backup. |
| IndicF5 | MIT, gated | Hindi, Tamil, Telugu | Needs reference voice audio. Backup. |
| Piper | Engine GPL-3.0, per-voice licences | Hindi and Telugu, no Tamil | Runs on CPU. Backup. |
| Meta MMS | CC BY-NC 4.0 | Hindi, Tamil, Telugu | Non-commercial licence. Not recommended. |
| Coqui XTTS-v2 | Coqui public model licence | Not checked | Not recommended. |

Transcribing:

| Option | Licence or cost | Notes |
|---|---|---|
| faster-whisper with Whisper large-v3 | MIT | Runs on the local GPU. **First choice.** |
| Groq Whisper | Free tier, limits to confirm | 20 requests a minute on the listed plan |
| Gemini Transcribe | Listed free tier | Not yet tested |

First result, on `fam-001-a`:

- **Audio:** Gemini 3.8 Flash TTS with the Charon voice produced 21.9 seconds of mono 16-bit audio at 24 kHz in 26 seconds.
- **Transcript:** every fact survived, including the negation, the dose and the duration.
- **Script difference:** Whisper writes English words in Devanagari, such as `डोलो 650` and `टॉंसल्स`, while the scripts keep them in Latin. So its text won't match evidence quotes exactly, and word error rate against the script would look worse than the real result.

Limits of this route:

- Whisper isn't Prisma. It proves the pipeline handles audio, but says nothing about Prisma's accuracy, keyterms or `codemix` output. Never report Whisper results as Gnani results.
- The final evals, keyterm test and demo must still use Gnani, since the challenge requires genuine use of its technology.
- Audio from a non-Gnani voice may be the fairer test for Prisma, because Gnani's own voice feeding Gnani's own recogniser could look better than real use. Worth testing.
- Record the audio source on every clip, and report results separately by source.

## How to run

From the repo root, after `pip install -r tools/corpus/requirements.txt`:

```bash
python -m pytest tools/corpus/tests
```

```bash
python tools/corpus/check_cases.py
```

```bash
python tools/corpus/check_cases.py --write
```

The first runs the tests, the second checks every case, and the third also refreshes the manifest and plain scripts. To rebuild seed records and the formulary:

```bash
python tools/corpus/make_seed.py
```

```bash
python -I tools/corpus/build_formulary.py
```

The formulary build reads `../DATA`, or the folder in `DATA_DIR`.

To set up local transcription, run these from the root folder, next to the repo:

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r Gnani-Hackathon/tools/corpus/requirements-audio.txt
```

On Windows, add `.venv/Lib/site-packages/nvidia/cublas/bin` and `.venv/Lib/site-packages/nvidia/cudnn/bin` to `PATH` before loading faster-whisper, or the GPU can't find its libraries. Get the model from the link in `data/DOWNLOADS.md`, and copy `.env.example` to `.env` for the Gemini key.

To set up the local model, install Ollama, set its model location to `models/ollama` in the root folder in the Ollama app's settings, then pull the model:

```bash
ollama pull qwen3:8b
```

The app ignores the `OLLAMA_MODELS` variable (C-31). Check with `ollama list`, and keep the Ollama app running during a pipeline run.

To build the medicine knowledge, from the repo root: download the labels, build the chunks, then embed them on the GPU from the separate `.venv-embed` environment (C-57). `search_local.py` tries questions against the result.

```bash
../.venv/Scripts/python tools/knowledge/download_openfda_labels.py
```

```bash
cd tools/knowledge && ../../../.venv/Scripts/python build_chunks.py
```

```bash
cd tools/knowledge && ../../../.venv-embed/Scripts/python embed_chunks.py --gpu
```

```bash
cd tools/knowledge && ../../../.venv/Scripts/python search_local.py "what is telmisartan used for"
```

To set up `.venv-embed`, create a venv in the root folder and install `fastembed-gpu==0.9.1` and `onnxruntime-gpu[cuda,cudnn]==1.31.1`. It needs an NVIDIA driver that supports CUDA 13.

To run the follow-up chat demo, start the API from the repo root (on Windows, `../.venv/Scripts/uvicorn` with `$env:PYTHONPATH = 'services/api'`):

```bash
PYTHONPATH=services/api .venv/bin/uvicorn voicerx.app:app --port 8000
```

Then the web app, and open http://localhost:3000:

```bash
cd apps/web && npm install && npm run dev
```

## Sources

- [Challenge page](https://www.gnani.ai/internship)
- [Participation terms](https://www.gnani.ai/great-indian-ai-internship-registration-form)
- [Gnani EULA](https://www.gnani.ai/legal/eula)
- [Gnani docs](https://docs.gnani.ai/llms.txt)
- [Gemini speech generation](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Groq rate limits](https://console.groq.com/docs/rate-limits)
- [Indic Parler-TTS](https://huggingface.co/ai4bharat/indic-parler-tts)
- [IndicF5](https://huggingface.co/ai4bharat/IndicF5)
- [Piper voices](https://huggingface.co/rhasspy/piper-voices)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Whisper large-v3 for faster-whisper](https://huggingface.co/Systran/faster-whisper-large-v3)
- [NVIDIA cuBLAS package](https://pypi.org/project/nvidia-cublas-cu12/)
- [Synthetic Medical Dictation](https://huggingface.co/datasets/modulate/synthetic-medical-dictation)

- Build task 0: completed; task tests and full suite passed.

- Build task 1: completed; task tests and full suite passed.

- Build task 2: completed; task tests and full suite passed.

- Build task 3: completed; task tests and full suite passed.

- Task 4: 225 tests pass. Live provider probe is running with bounded network retries; deterministic implementation continues while it finishes. Live outcome will be recorded before Task 16. This overlaps the live verification only; no implementation tasks are delegated.

- Build task 4: completed; task tests and full suite passed.

- Build task 5: completed; task tests and full suite passed.
- Task 4 live verification: Gemini gemini-3.8-flash and Ollama qwen3:8b each returned a valid tiny-schema object on one attempt. No adapter changes were needed.

- Build task 6: completed; task tests and full suite passed.

- Build task 7: completed; task tests and full suite passed.

- Build task 8: completed; task tests and full suite passed.

- Build task 9: completed; task tests and full suite passed.

- Build task 10: completed; task tests and full suite passed.

- Build task 10b: completed; task tests and full suite passed.

- Build task 11: completed; task tests and full suite passed.

- Build task 12: completed; task tests and full suite passed.

- Build task 13: completed; task tests and full suite passed.

- Build task 14: completed; task tests and full suite passed.

- Build task 14b: completed; task tests and full suite passed.
- D-73: Cached clean end-to-end fixture exposed a false negation on Hindi combining marks. Word-cue boundaries now include Unicode marks; all ten sabotage cases still block. Full suite: 317 passed.

- Build task 15: completed; task tests and full suite passed.
- D-74: Inspection found whitespace normalization erased newline medicine boundaries. Preserve a same-length boundary copy; a regression now blocks doses borrowed across lines. Full suite including scorer accuracy checks: 325 passed. The in-flight first run will be rechecked from cached replies after this fix.
- D-75: CLI reapproval could reuse a prior approved artifact before validating a subsequently altered draft. Always validate the current draft first, then reuse the original approval timestamp only for identical content and approver. Regression and full suite: 326 passed.
- D-76: Live full-length PDF inspection found footer overlap and a one-line second page. Footer now uses CSS page-margin boxes with escaped content; tighter spacing keeps fam-001-a on one readable page. Hindi, watermark, medicine columns, review block and footer checked visually. Full suite: 326 passed.
- D-77: Evidence audit found that a model-supplied known medicine name could disagree with its genuine name quote, or add an unstated strength. Exact matches now require the quoted name to resolve to the same product; ambiguous quotes stay ambiguous and conflicting identities block. Two regressions and the full suite pass (328 tests).
- D-78: Report evidence audit reproduced an invented-side line and an unknown finding rewritten as positive, neither blocked by the original lexical checks. Added blocking checks for unsupported sides and missing unknown wording, preserving the documented lexical-check limitation. Full suite: 330 passed.
- D-79: Task 16 cloud retries took about 23 minutes for the first two cases. Added optional run_cases(..., workers=1, selected=None) and CLI --workers 1..4 (default 1) to overlap independent families; visit order is preserved and Ollama requests remain serialized. Cache writes now use unique temporary files and synchronized replacement. This changes evaluation scheduling only; implementation remains one agent, tasks in order. Full suite: 332 passed.
- Task 16 execution note: Updating the PDF template while the first process was alive caused fam-001-b rendering to fail with a missing CSS filter. Restarted against cached model replies; both first cases then rendered successfully. No failed-render report was retained.
