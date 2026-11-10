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
| Gnani API key | In `../credentials` and the ignored `.env` (D-104). Prisma v3.0 accepted it on 10 trial requests. | Find out what a request costs in credits (Q-03) |
| Repo | Implementation is on `aditya/extraction-report`, pushed to origin; no merge or PR. `main` is unchanged. | Review the branch, then team merges when ready |
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
| Application code | Doctor workspace and Supabase pipeline include verified patient WhatsApp links across visits, automatic approved-PDF delivery, requested native prescription voice notes, saved questions/replies, private lab originals and summaries, and next-visit history. See the connected patient journey entry below and docs/whatsapp-integration.md. | Production authentication/deployment, approved Meta templates outside the reply window, clinical/language review and amendments |
| LLM | Groq `openai/gpt-oss-120b` is the working model, on two keys (D-85, D-88). Gemini (quota) and local `qwen3:8b` (safe but noisy) are fallbacks. | Compare Gemini once its daily limit resets |
| Evals | Typed and Whisper runs scored for Groq and the local model; see Verification. Prisma trial scored privately (D-91). | Score all Prisma clips, privately |
| Medicine knowledge | In Supabase and searchable: 46,540 chunks from openFDA labels, NLEM 2022 and Jan Aushadhi, embedded with bge-base on the GPU, plus 246,068 Indian products for brand lookup (D-94 to D-103, C-55 to C-60). 382 MB of the 500 MB free limit. Not used by the pipeline or any app yet. | Decide what the knowledge does first (Q-23); prefer single-medicine labels and the right route for brand questions |

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
| D-126 | Add the hospital pharmacy's stock to medicine suggestions: an in-stock bonus when ranking, a stock badge on each prescription line, and a one-click swap to an in-stock product with the same composition. | Doctors prescribe what the patient can collect on the way out, which is the hospital's revenue case. Design notes in the 5 Nov entry below. | Proposed |
| D-127 | Rank by availability only, never by margin, and never change a line without the doctor's click. | The Supreme Court (Siddharth Dalmia v. Union of India, 3 Mar 2025) asked states to stop hospitals compelling in-house pharmacy purchases, and the case returned in Sep 2026. A margin-ranked or forced pharmacy would be a liability in the pitch and in practice. | Proposed |
| D-128 | Build stock import first as a CSV/Excel upload with an "as of" time; add webhook push and polling connectors after the hackathon. | Every Indian pharmacy package can export a stock report; live connectors depend on each vendor. | Proposed |

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

### Credentials

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-104 | `../credentials` holds every key, one file each. `tools/credentials/sync_env.py` copies them into the ignored `.env`, printing only which variables changed; the database connection string is cleaned on the way (template brackets dropped, password URL-encoded, `sslmode=require`). It still looks in the root folder for a file not yet moved (`database_connect_supabase.env.txt` is there now). `tools/key_leak_check.py .` with no key file checks every key, plus the database password raw and encoded, against all repo files and git history. | Aditya moved the keys into one folder. One sync step means a rotated key reaches the code without hand edits, and one check covers every secret. Mistral's file is checked but not synced (Mistral is dropped). | Aditya (folder); Assistant (sync and check) | Confirmed |

### Doctor workspace

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-105 | Until Supabase Auth is set up, the app offers a development sign-in: with `APP_DEV_LOGIN=1` in `.env`, it lists the synthetic seeded doctors and signs in as the one chosen, with no password. It only reaches synthetic doctors in synthetic organisations, says so on screen, and is off unless set. Password sign-in returns "not configured". | DESIGN.md asks for Supabase Auth sessions, but creating users in a hosted identity service is for Aditya to do. A labelled, synthetic-only sign-in keeps the rest of the contract real: server-side sessions in an HttpOnly cookie, a CSRF token on every unsafe request, an Origin check, and identity taken only from the session. | Assistant | Assistant call |
| D-106 | Build the workspace as DESIGN.md section 4 sets out, with these choices: FastAPI in `services/api/voicerx/app` serving `/api/v1` and a plain HTML, CSS and JavaScript app from the same origin (no build step; Node.js isn't installed); application tables in a private `app` schema in the same Supabase Postgres (not exposed through Supabase's Data API); a worker thread that claims runs and artifacts from those tables with leases (`FOR UPDATE SKIP LOCKED`), bounded attempts and a wait-and-retry on a provider's daily limit; and the engine called as functions, never through its CLI. Approval inserts its file jobs in the same transaction (an outbox). Approved files are written to `runs/app/`, ignored by git, until private storage is set up. | It follows the contract's architecture with the fewest moving parts that still keep work durable across restarts. The look is the prototype's: its colours, fonts, patient list and record card. | Assistant, from DESIGN.md as Aditya asked | Assistant call |
| D-107 | The first slice covers: sign-in, the patient list and search, patient history, starting a visit, typed or pasted text (with the synthetic sample scripts for that patient as a shortcut), live stage progress, the review screen (every issue with the corrections that fit its target, each requiring a reason; report lines with their cited findings and quotes highlighted in the source; the structured prescription), draft PDF preview, approval checked against the expected version and fingerprint, approved PDF and FHIR downloads, and reference search scoped to a medicine's ingredients. Left for later: Supabase Auth, recording and Prisma, uploads, amendments of approved visits, reprocessing a visit that already has a draft, patient and caregiver access, questions and check-ins, delivery, and organisation administration. | DESIGN.md section 13 orders the work; this is its first two steps plus the review and approval core, enough to run the whole doctor journey end to end. | Assistant | Assistant call |
| D-108 | Move the database to a new Supabase project in South Asia (Mumbai, `ap-south-1`), project `kymzybfrtirzpegpibcj`. The knowledge base was reloaded from the saved vectors and the app schema recreated; `sync_env.py` now derives `SUPABASE_URL` from the connection string. The Frankfurt project (`rftuxwsnfinuygewssas`) holds only the old copy and a few synthetic test visits; Aditya deletes it once the new one is confirmed. | Every page waited on Frankfurt. From here a query round trip is now 21 ms and a new connection 170 ms. Health data also stays in India. | Aditya | Confirmed |
| D-109 | Recording works in the app. The browser records with `MediaRecorder` (pause, resume, stop, discard, a level meter, playback before upload, a 20-minute cap, the microphone released on leaving the page); a file can be uploaded instead; typing stays available. The doctor confirms the patient agreed, and the server also requires `recording` in the patient's consents, then reads the real length (2 seconds to 20 minutes, at most 40 MB) and keeps the original file with its checksum and the consent confirmation. The worker transcribes with Prisma v3.0 (`codemix`, no keyterms per D-92), cutting recordings over 29 seconds at their quietest moment and sending each piece with the text before it; a truncated reply, an unreachable service or silence stops the run with that reason rather than producing a shorter or empty note. A retry reuses the transcript already made. Rate limits and server errors wait and retry. The review screen plays the recording beside the transcript. | Aditya asked for the record button to work end to end with Prisma. DESIGN.md 5.2: real capture, consent as a record, the server checks the media, no truncation to fit a provider. | Aditya | Confirmed |
| D-114 | Replace the prototype's look (D-106) with the "Ledger" direction: cool grey ground, white panes with 1 px hairlines and no shadows or gradients, one slate-blue accent (`#3A5A94`) for primary actions and selection, IBM Plex Sans with IBM Plex Mono for record numbers, doses, citation ids and transcripts, and 6–8 px corners. Layout and behaviour are unchanged apart from dropping avatars from the patient list and patient headers. The sign-in page lists the languages the app offers rather than claiming any as tested. | Aditya asked for a minimalist design that is easy on the eyes. Three directions (Paper, Ledger, Dim) were drawn as wireframes on a private design canvas, and Aditya chose Ledger. This departs from DESIGN.md 3's "warm neutral styling"; DESIGN.md is in the root folder and was not edited. | Aditya | Confirmed |
| D-116 | The report reads as a hospital outpatient summary (Aditya's reference, kept outside the repo): an opening "Patient seen in the outpatient clinic on …", then Present problem, Objective findings & investigations, Assessment, Treatment advised (with the prescription table), Tests ordered, Referrals, and a bold closing review line. Each line is a full sentence and may join related items of its section; a section's sentences run on as one paragraph in the app and the PDF, each still selectable for its sources. Storage keeps the 11 sections, so older reports, approvals, FHIR and the eval are unchanged. The PDF drops the "Not discussed" line; the review screen keeps it. Prompts `report-v3` and `extract-v4` (kinds defined: an order is a test; physiotherapy, rest and diet are plan or advice; a later re-examination is follow-up). The report still adds no causes, links or interpretations the doctor didn't state, unlike the reference. | One fact per line and stiff labels read as machine output. | Aditya approved the design | Confirmed |
| D-117 | No typed reasons in the review screen. "Accept" (confirming one's own order, or a warning) saves in one click; edit forms show only their fields and "Save"; removals ask once ("Yes, remove"). The screen supplies a plain reason for each action ("Dose set by the doctor.", "Confirmed by the doctor as their own order."), and the server still stamps who and when from the sign-in. DESIGN.md section 7 still holds: every correction has a nonblank reason, supplied by the screen as it allows. Checked in the app on the test visit: a warning accepted in one click (version 3); the dose form has no reason field. | Aditya: the doctor is the one confirming; typing a reason for each click wastes their time. | Aditya | Confirmed |
| D-118 | Medicines are completed automatically, marked, and checked by the doctor's approval of the whole draft. This reverses "nothing is applied without a click" (D-92, spec 2026-11-03 part B.4) for clear cases only. After the checks, a completion step (`pipeline/complete.py`) names the product when the evidence is clear: the doctor's earlier choice for these heard words; a generic said by its ingredient (`data/formulary/generic_names.txt`, 662 names from the dataset); a close spelling with one formulary candidate and an agreeing strength; or a clear match over all products (`suggest.confident_choice`: sound 0.88, or 0.75 when a stated strength agrees; a listed or widely sold product; no other well-known brand of another composition within 0.05, or 0.08; no brand-family sibling of another composition within 0.15). It then fills the standard dose, food and daily times (D-115), and a bare "one" takes the product's unit. Every filled field is marked in `filled` and tagged on the review screen; a doctor's edit removes the mark. Still left for the doctor: bare names with siblings ("Pan"), a strength the product lacks, names that match nothing well known, allergy conflicts, garbled instructions. The evaluation runner keeps measuring raw extraction: its gold cases expect a missing-dose flag. | Aditya: approving 9 of 10 medicines by hand defeats the product; target 1 to 2 in 10. Measured before: 26 of 28 medicines needed a hand. | Aditya approved, with the reversal stated | Confirmed |
| D-119 | Remembered medicine choices are shared across the clinic. Each confirmation still records its doctor; lookups add up every doctor's confirmations for the same heard words (`suggest.clinic_choices`), and a clear lead fills the product in automatically (D-118), tagged "Chosen before in this clinic". Two products confirmed equally often stay a question. Suggestion prompt `suggest-v4`; the eval tool's `--as-doctor` option is gone. | One confirmation now teaches the whole clinic instead of one doctor. Closes Q-25. | Aditya | Confirmed |
| D-120 | For an adult (18 or over) with no form said, a brand means its tablet or capsule: its syrup, suspension, drops, solution or injection neither win nor make the choice ambiguous, and a sachet, granules or powder of the same drugs (a children's strength) yields to the tablet or capsule. A form said aloud always stands. A product on the clinic's own list (formulary or clinic-added) is taken at sound 0.84 rather than 0.88, with the same margins over well-known rivals. | Aditya: prefer tablets. Two of the new-clinic misses were a brand beside its children's form and a listed product just under the bar. | Aditya | Confirmed |
| D-121 | Gujarati dictation is supported. Prisma gets `gu-IN,en-IN` (as Hinglish gets `hi-IN,en-IN`), and the recording screen and sign-in page offer Gujarati. The parsers know Gujarati numbers, tablet/capsule/spoon, days/weeks/months, morning/afternoon/evening/night, food and meal words with their relations ("નાસ્તા પહેલાં", "before નાસ્તા"), twice-a-day and as-needed phrases; the checks know Gujarati negation (નથી), hedges, sides, first person, prescribing and linking words; English written in Gujarati script is read back, and Gujarati names are spelt in Latin letters via their Devanagari counterparts. Number words no longer match inside a word ending in a vowel sign ("છે" is not six). Prompt `extract-v5`. Not done: patient-facing Gujarati instructions (the patient box has Hindi, Tamil and Telugu templates only). | Aditya tested a Gujarati recording; its three flags all came from Gujarati being unknown. Replayed: 3 blocking to 1, the ambiguous "four five days". | Aditya | Confirmed |
| D-122 | Medicines are chosen and instructed from the keyboard. "Add medicine" (or the space bar on the review screen, when no field or button is selected) opens a picker: the visit's common choices first, a search of every product as the doctor types; ↓↑ and Enter pick. Then rows Days, Times a day, Which time (only the combinations that fit the times), Dose, Food: ↓↑ moves between rows, ←→ changes the value, Enter saves, Esc steps back. Dose and food start from the standard instructions (D-115), once-a-day from the ingredient's usual time. "Edit instructions" on a matched medicine opens the same rows with its values. A new correction `add_medicine` adds a medicine with its instructions in one audited step. The common choices (`app/shortlist.py`, `app.medicine_shortlists`, prompt `shortlist-v1`) come from the model, given the visit's present findings, as generic, usual strength and an Indian brand; each becomes a real product only when a well-known brand sounds right and holds exactly the named ingredients, else the generic, else it is dropped. Made with each draft; older visits make it on first open. Product search now ranks widely sold products first and carries each product's standard food and time. | Aditya: picking a medicine and typing its numbers stalled the doctor; the dictated fields are right, the medicine step is slow. | Aditya | Confirmed |
| D-123 | Prescribing runs medicine after medicine: Enter saves one and opens the picker for the next ("Medicine 5 · Esc when done"), Esc ends the round. Medicines already on the prescription drop out of the common choices. The choices come grouped by purpose, up to eight: the main treatment, then the usual companions (a stomach protector beside a painkiller, a supplement where usual), each tagged (Pain, Acidity, Supplement, Muscle…); prompt `shortlist-v2`. Cached v1 lists were cleared to rebuild. Tested by keyboard on the knee visit: the list read Pain, Acidity, Supplement, Supplement, Muscle; Pantocid 40 saved once in the morning before food (version 4), the next picker opened by itself without it, Esc closed. | Aditya: after one medicine there was no way on to the next (one for pain, one for acidity, a nutrient). | Aditya | Confirmed |
| D-124 | The app_v2 design is the interface: `/` opens `web/static/app_v2/index.html`. The original stays at `/v1` (`web/index_v1.html`). Only the look differs: app_v2 loads the same `/static/app.js` and `/static/app.css` as the original, plus its own `app.css` and `presentation.js` (initials, Record / Check / Approve indicator, text size, background motion). Its earlier copies of the script and stylesheet were removed so a workflow fix reaches both pages. | Aditya: "we are going with this UI instead of ours, rest everything is same; keep the initial version as well." | Aditya | Confirmed |

### Medicine names and timing (spec `docs/superpowers/specs/2026-11-03-medicine-resolution-design.md`)

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-110 | Meal phrases give both a food rule and a slot: before/after/with (pre-, post-; से पहले, के बाद, के साथ) breakfast, lunch, dinner or supper (नाश्ता, दोपहर का खाना, रात का खाना, or the English word in codemix). Breakfast is morning, lunch afternoon, dinner and supper night. No timing, or a daily frequency equal to the meals named, becomes that slot; a stated slot that contradicts the meal stays as said and is flagged; different relations in one phrase give nothing. A missing dose still blocks. | In Aditya's recordings, "before breakfast" and "once a day post-lunch" were quoted but never parsed, so food and timing came out empty. | Aditya (plan approved) | Confirmed |
| D-111 | Products come in tiers, shown in the id: the reviewed formulary (`p-…`, exact matches applied automatically as before), the Indian Medicine Dataset (`in-…`, unverified) and clinic products (`cp-…`, added by a doctor, pending review; a hospital's drug master can be imported into the same table). Outside the formulary a product is only ever a suggestion the doctor confirms; once chosen it is frozen into the draft like any other. | Many brands a doctor names are not in the 25-row formulary, and some (a collagen sachet) are in no list at all. The doctor can add one while fixing the flag. | Aditya (plan approved) | Confirmed |
| D-112 | For a medicine not matched exactly, the worker adds a step after the draft: candidates by spelling and sound (Indian-English letter swaps, vowels kept as syllables, strengths compared), each candidate's drug class, NLEM category and knowledge-base fit with the visit's context, and a Groq ranking with one-line reasons limited to the candidates given. The code decides the order (sound, a lead for formulary and clinic products, the doctor's past choices, fit, the model's rank as one input, a penalty for a disagreeing strength); the matcher's own formulary candidates always lead. The first suggestion is called "likely" only with a clear lead (sounds close, nothing else almost as close, no sound-alike sibling such as Pan 40 beside Pan-D, strength not disagreeing, and the model or the doctor's history agreeing); otherwise the screen says "possible matches". Nothing is applied without a click, the audit records what was heard and what was chosen, and each confirmation is remembered per doctor. | Aditya asked for the knowledge base to work out misheard names from context. The first measurement showed the model alone ranking by use over name and inventing confidence; the safety decisions (order and "likely") had to move into code. | Aditya (plan); Assistant (method) | Confirmed |
| D-113 | Two more inputs to medicine suggestions. (1) Spoken letters: a brand whose later words are letters (Pan-D, Montair-LC, Taxim-O) is also matched as those letters are said, apart and joined ("pan di", "pandi"), with "ee"-sounding endings folded on both sides, because speech recognition writes "Pan-D" as one word. (2) Popularity: each Indian-dataset product gets 0 to 1 from the dataset's own order (C-66), and up to 0.15 for it; never more than a clinic listing, and the model is told which brands are widely sold (prompt `suggest-v3`). Popularity only orders; "likely" still needs a clear lead on sound alone. | A new recording put an obscure sound-alike first and called it likely, over Pan-D. Measured on 11 private cases: right product first 8 to 9, in the top three 10 to 10, a wrong product shown as likely 1 to 0. | Aditya chose these two fixes first, from three offered; the Prisma confusion run waits | Confirmed |
| D-115 | Standard instructions for common medicines, by ingredient (`data/rules/standard_instructions.yaml`, 35 rules, `reviewed: false`): the food rule and the time for a once-daily dose, each marked label or usual practice. A combination takes what its ingredients agree on. They fill only what was left unsaid, and only when the doctor accepts: dose 1 for a tablet or capsule, the food rule, and the times for a daily frequency (once: the ingredient's time; twice: morning and night; three times: adds the afternoon; four: every slot). Duration and a missing timing are never filled. Accepting uses the existing set_dose, set_food and set_timing corrections with a reason naming the rule, so the audit is unchanged. One button accepts all; choosing a suggestion also brings its product's standard values in one click. "Daily" stays once a day, never morning and evening, which would double the dose. Frequency words added: roz, QID/QDS, thrice daily, TID/BID, HS (night). | Aditya: doctors leave out what everyone knows (Dolo 650 after food) and every gap was a manual fix. | Aditya approved the design | Confirmed |

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
| C-61 | The two Supabase key files left the root folder; Aditya moved every key file into `../credentials`. | Nothing broke, since the keys were already in `.env`. See D-104. |
| C-62 | First measurement of suggestions on 9 real mishearings: right product first 4, in the top three 5, and the model ranked a wrong product first in 4. Causes: a sound key without vowels made dozens of unrelated brands score as perfect matches; the formulary had no lead over 246,000 near-identical names; formulary candidates could be dropped; the model ranked by use or strength over the name, put an injection first for "before breakfast", and offered products for names that match nothing. | Vowel runs kept as one letter, spelling and sound averaged, a lead for formulary and clinic products, formulary candidates always first, stricter instructions, and the order and the "likely" label decided in code (D-112). Result: 7, 8 and 0 (C-64). |
| C-63 | Formulary products were still cut off: the name search kept its top 40 before the formulary lead was applied, and dozens of similar 40 mg names filled it. | The lead applies inside the name search. |
| C-64 | Two runs of the same case gave different lists. Each medicine was searched by its full words and by its quoted name, and the quoted name carries no strength; whichever copy survived depended on Python's set order, so some results escaped the strength rule. And a doctor's past choice was added with a sound score of 0, so even its lead couldn't lift it. | Names searched in a fixed order and every candidate's strength judged against the full heard words; added candidates scored like the rest. Results now identical under two hash seeds: right product first 7 of 9, in the top three 8 of 9, a wrong product shown as likely 0 of 9. |
| C-65 | The search listed Pan-D as "Pan capsule": formulary aliases are indexed under the alias. | Results show the product's own label. |
| C-66 | The Indian Medicine Dataset lists each first letter's products in what looks like sales order: under "P" (9,258 products) PAN 40 is 2nd and Pan-D 3rd, while the obscure sound-alikes Panday and Pandu are 1,521st and 3,417th; Augmentin, Combiflam, Montair-LC and Wysolone are each in their letter's top 3. The dataset doesn't say so. | Used as an unverified popularity signal (D-113), `1 - ln(rank) / ln(letter total + 1)`, 0 for discontinued products; stored as `indian_products.popularity` by `upload_supabase.py --popularity-only`. |
| C-67 | The patient list labelled every open draft "Draft · ready to approve", even one with 4 blocking issues. The list query returned only the open visit's state, not its blocking count, so the label fell back to "ready". | `list_patients` now also returns `open_blocking`, counted from the open visit's latest report the same way the patient page counts it (null when there is no report yet), and the list passes it to the label. Checked against the running API: for all three patients with an open visit, the list's count equals the patient page's (null, 1 and 4). 303 unit tests pass; the query has no unit test because the app tests have no database. |
| C-68 | Joined sentences were blocked: the report check flagged any line citing both present and absent findings (`mixed_negation`), so "sore throat for 3 days, no fever" could never be written. | The check now requires a negative word in any line that cites an absent finding, and drops the mixed rule. It stays lexical: it can't tell which item a negative belongs to. |
| C-69 | On the evening of 3 Nov, Windows Application Control blocked `mmh3`'s compiled file in `.venv` ("An Application Control policy has blocked this file"). fastembed imports it at load for BM25 sparse embeddings, so the embedding model failed and with it knowledge search and the context step of medicine suggestions. Every other compiled package still loads. | The app registers a stand-in `mmh3` that refuses to hash when the real one can't load (`knowledge.stand_in_for_mmh3`); the app never uses sparse embeddings, and the blocked file is never run. Windows' policy is left as it is: changing it is Aditya's call. |
| C-70 | Most phrase flags were false: the check only looked after the name and within its sentence ("one Pan D", "the dosage for Pan D is... One after breakfast"), required word-for-word copies, and differed on the nukta ("ज़रूरत"/"जरूरत"). And every "I am recommending ..." sentence marked the doctor's own medicine as "not clear who said this". | The window starts at the sentence (after any earlier medicine) and, when nothing but linking or form words follow the name, runs through the next sentence; never across a line or past the next medicine. Copies may skip up to two words; the nukta is ignored; food and duration said inside the timing phrase are used. First person with a prescribing verb is the doctor. |
| C-71 | A 4 Nov recording named one painkiller twice and speech recognition spelt it two ways; its instructions followed the second spelling, which matched no medicine's quote, so the duration was flagged as "may belong to another medicine". The same dictation showed the C-70 window reaching back too far: Pan 40 took "for three days" said for paracetamol just before it. And the card said "Unbound phrases: duration_phrase". | A later word of five letters or more that closely matches the first word of a medicine's quote (75%), and is not part of another medicine's name, counts as a mention of it. Before a name, only four words count. The card says what was heard ("Said away from this medicine: duration 'for three days'") and offers "Use 'for three days'" in one click, beside the edit buttons. Replayed: the painkiller completes; Pan 40 is now flagged instead of borrowing. |
| C-72 | A 4 Nov Hinglish recording had 9 blocking issues. Four were left-knee findings whose short quotes ("pain और instability है") leave out the "left" said just before them. Five came from Prisma writing the English in Devanagari (a brand name, "पैरासिटामोल", "वन कैप्सूल", "ब्रेकफास्ट के पहले", "ओरली"); the parsers and the matcher read Latin letters only, "से" after the name stopped the next-sentence rule, and "के पहले" was not a known meal relation. | A side said in the quote's own sentence supports it when that sentence names no other side. `pipeline/romanise.py` turns common dictation English back from Devanagari (numbers, forms, meals, times, orally) before parsing, and spells other Devanagari names in Latin letters for matching ("parasitamol" for paracetamol); generics also match by sound, with 'c' before e or i read as 's'. Hindi linking words count like "is"; "के पहले" means before; a route given as the timing is the route. Replayed: 9 blocking to 0, one warning (paracetamol's strength not said). |
| C-73 | The first shortlist for a knee visit listed "ROCIN 500 (azithromycin)" for the model's "Crocin 500, paracetamol, mild pain relief": the brand matcher took the closest sound with the same strength. And the edit rows ignored the arrow keys, because they took focus before they were on the page. | A brand is used only when its ingredients are exactly the named generic's (spelling, sound or close match); otherwise the generic. Focus moves to the rows once they are shown. Tested by keyboard alone: added Paracetamol 500 for 7 days three times a day (version 2), changed Combiflam to 7 days (version 3), searched "telma" (Telma 40 first, once in the morning), Esc closed without saving. |
| C-74 | PDFs stopped printing on 4 Nov: 13 tests failed with "headless browser failed to produce a PDF". Headless Edge 156 started and exited with code 0 in under a second without loading the page or writing a file, for file and data pages alike, with or without the tool sandbox, and with every flag tried (old headless, no sandbox, no field trials). Headless Chrome printed the same page. No approved visit was affected: all 10 export jobs were already ready. | Test-first: the PDF step lists every installed browser (`PDF_BROWSER`, Edge, Chrome, Chromium) and hands over to the next when one exits without a PDF; a browser that stalls still stops the attempt (C-41). All 381 tests pass; the real print test makes its PDF through Chrome. |

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
| Built the doctor workspace, first slice | Read DESIGN.md, DASHBOARD-SPEC.md and the design review in the root folder, and the prototype they cite. Built the app schema and seed script, sessions, the report view and correction checks, the clinical service, the worker, the API and the web app (D-105 to D-107); 17 new tests. Ran the whole journey in the browser: see Verification. |
| Restyled the doctor workspace (3 Nov) | Drew three minimalist directions, then the full doctor journey in the chosen one. Rewrote `services/api/web/static/app.css` on the new tokens, changed the sign-in markup and removed avatars in `app.js`, and switched the fonts in `index.html` (D-114). Checked sign-in, the patient list, patient history, capture, and the review screen with a selected line and medicine suggestions in the browser at 1440 px and 375 px: no console errors and no sideways scrolling. The processing screen was not seen live, because no run was in progress. |
| Built the medicine knowledge chunks | Downloaded openFDA's label export (14 files, 262,903 labels), and wrote `tools/knowledge/` test-first: a name map, label selection and chunking, an NLEM 2022 parser and a Jan Aushadhi grouper (25 tests). The build gives 1,322 labels as 31,989 chunks, 381 NLEM medicines and 110 Jan Aushadhi groups. Read samples from each source and fixed what they showed: brand names in titles, NLEM table headers and notes inside categories, and form words inside Jan Aushadhi ingredients. See D-94 to D-99. |
| Built a code knowledge graph | Ran `graphify update .` on the repo: 725 nodes, 1,742 edges, 35 communities, from code only with no model calls. Output is in the git-ignored `graphify-out/`. Query it with `graphify query "<question>" --budget 600` before reading whole files. |
| Implemented extraction/report tasks 0–15 | Contracts, references, number/schedule parsing, medicine matching, both model stages and checks, frozen drafts, audited corrections, approval, patient-language templates, PDFs, FHIR, runner, sabotage fixtures and scorer. 332 tests pass; Task 16 is in progress. See build log below for per-task checkpoints and D-72 onwards for deviations. |

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
| Doctor workspace | `services/api/voicerx/app/` (API, worker, schema in `migrations/`), `services/api/web/` (the web app) | `python -m voicerx.app.migrate` once, then `uvicorn voicerx.app.main:app`; see How to run |
| Medicine knowledge chunker | `tools/knowledge/` | `download_openfda_labels.py`, then `build_chunks.py`; output in `../DATA/knowledge/chunks/` (D-98) |
| Prisma transcription | `tools/corpus/transcribe_prisma.py` | Prisma v3.0 REST, optional formulary keyterms; output is git-ignored (D-91) |
| Local run artifacts and response cache | `runs/` | Ignored by git; synthetic inputs only |

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
| Doctor workspace in the browser, 3 Nov | Signed in as synthetic Dr Parth Shan; opened Suhani Agrawal (pat-008); started a visit; inserted the `fam-008-a` sample; processing showed each stage and produced draft v1 with its three expected blocks (uncertain "acid reflux", ambiguous Pan, unrecognised Mucaine gel). Chose Pan 40 (v2), edited the line to "Suspected acid reflux" (v3), removed Mucaine gel (v4): nothing left flagged. Draft PDF preview: a valid 77 KB PDF. Approved v4: one approval row, versions 1 to 4 kept with the approved snapshot, the worker rendered the PDF (80 KB, no draft watermark, approver and version 4 printed) and both FHIR bundles, and the audit trail lists every step. Reference for PAN 40 is limited to pantoprazole and returned label and NLEM passages. A new English consultation for pat-003 ran live on Groq in 19 seconds with no blocks and Montair LC matched. |
| Recording path, 3 Nov (Mumbai database) | Over HTTP: an upload without the consent confirmation and a file that isn't audio were refused; an 18.4-second synthetic clip (`fam-008-a`) was transcribed by Prisma in about 1.5 seconds and gave the same three blocking issues as the typed run; a 32.8-second clip (`fam-010-b`) was split into two pieces and processed live in 13 seconds; the stored recordings play back. In the browser: the microphone is blocked inside the Browser pane, and the app said so and offered upload or typing; with a generated tone standing in for the microphone, recording, pause, resume, playback, discard and upload worked, the server decoded the browser's WebM, and Prisma's "no speech" stopped the run with that reason. A first version reported a 3-second recording as "0:00" (the length was read after the recorder had stopped); fixed. Real speech into a real microphone: Aditya recorded in his own browser and reports it working; the server log shows four browser recordings accepted (3 Nov). Prisma accuracy details are in the private note (Q-04). 263 API tests pass, 8 of them new for the Prisma client. |
| Medicine suggestions, 3 Nov (`tools/eval/medicine_suggestions.py`; cases in the private `../prisma-medicine-cases.json`, Q-04) | 9 cases: 6 misheard brands with a right answer, 2 brands in no list, 1 sound-alike trap. Right product first 7, in the top three 8, a wrong product shown as "likely" 0. Measured as the doctor who had confirmed one choice: first 8, top three 9, wrongly likely 0. Neither brand that no list holds was presented as found. |
| Meal timing and suggestions in the app, 3 Nov | A new typed visit from Aditya's knee consultation: "once a day post-lunch" became the afternoon slot after food, "before breakfast" the morning slot before food, a medicine with no meal said kept no timing. The worker's new step ran; Pan 40 came first for its heard words as the doctor's earlier choice; "possible matches" (not "likely") everywhere else. A product with no composition was refused; Colaquick was added as a clinic product, chosen, and appeared in the draft as "COLAQUICK SACHET (COLLAGEN PEPTIDE+VITAMIN C) 10G+40MG", then in search. The 25 typed cases, rerun from cache with the new parser, score exactly as before. 299 API tests pass. |
| Workspace safeguards, 3 Nov | No CSRF token: 403. Forged token: 403. Correcting an approved visit: 409. Repeating an approval: returns the recorded one, no second row. Unknown visit: 404. No session: 401. Sessions survive a server restart. 255 API tests pass, including the 17 new ones. |
| Supabase upload, 3 Nov (`upload_supabase.py`) | `knowledge_chunks` 46,540 rows (308 MB with indexes), `indian_products` 246,068 rows (59 MB), `knowledge_words` for keyword weights. Database 382 MB of the free plan's 500 MB. Upload about 90 seconds, index build about 2 minutes. Rerun-safe: each run replaces the contents in one transaction. |
| Supabase search after C-60 (`search_supabase.py`, `match_chunks`) | "what is telmisartan used for": Telmisartan Uses first (0.854). "can I take ibuprofen with telmisartan": Telmisartan Interactions first. "domperidone uses": its NLEM entry first (no US label exists). "Jan Aushadhi generic for diabetes": Anti-Diabetic first. "paracetamol overdose liver damage": six acetaminophen Overdose sections. "azithromycin in pregnancy": azithromycin Pregnancy sections. Brand: "Telma 40" resolves to telmisartan, then its side effects and pregnancy sections; "Dolo 650" to acetaminophen, then dosing. Weak: a brand's search returns combination products as well as the single medicine, and ignores the route ("Dolo 650 maximum dose" puts intravenous acetaminophen dosing first). |
| Supabase database connection, 3 Nov | Session pooler (`aws-1-eu-central-1`, port 5432) with psycopg 3.3.6: connected to PostgreSQL 17.11. The connection string kept the template's square brackets around the password, and the password holds an `@`; the copy in `.env` (`SUPABASE_DB_URL`) drops the brackets and URL-encodes the password, and Aditya's file is unchanged. pgvector 0.8.2 turned on in the `extensions` schema, with `halfvec` available. No tables yet; database 10 MB. Password leak check on the repo and its history: clean. |
| Supabase connection, 3 Nov | Project `rftuxwsnfinuygewssas`. Auth health with the publishable key: HTTP 200. Schema listing with the publishable key: refused (401, "Secret API key required"), as intended. Schema listing with the secret key: HTTP 200, no tables yet. Whether pgvector is on can't be seen through the API. Leak check on both keys: clean. |
| Unit tests after the Prisma source was added | Runner and scorer suites pass, including a new test that each speech source reads its own folder |
| Medicine suggestions after D-113, 3 Nov | API 303 tests and knowledge tools 40 pass. Popularity set on 246,068 products. Private eval (11 cases, two added from the 3 Nov recording; the two Colaquick cases now expect the clinic product Aditya added): before 8/11 first, 10/11 top three, 1 wrong "likely"; after 9/11, 10/11, 0. Still wrong first: one Pan 40 mishearing (sounds closer to the Pan-D family; fixed after one confirmation) and Montair-LC, which the model ranks below a closer-spelt obscure LC brand. Stored suggestions replaced (`backfill_suggestions --all`). |
| Report and standard instructions after D-115, D-116, 3 Nov | API 325 tests and knowledge tools 40 pass; key leak check clean. Offline rewrite of the 3 Nov knee visit (extract-v4, report-v3): every section full sentences, physiotherapy under Treatment advised, the re-examination as the closing review, no issues. In the app: the summary headings, "Accept all" for standard values, and one-click suggestions (Combiflam chosen with "1 tablet" in one save) work; the PDF renders the new layout. Eval `typed-groq-4` stopped at 4 of 25 cases (Groq daily quota): fam-001-a unchanged; fam-002-a/b one more fact and one more correct section; fam-003-a facts found 4 to 8 of 8 but two unexpected `negation_mismatch` blocks. The other 21 cases still need a run when the quota resets; the partial score file is not committed. |
| Medicine completion after D-118, 4 Nov | API 347 tests pass. Replay of all 28 medicines in the 13 stored visits (fresh extraction, new checks, completion with each visit's doctor's earlier choices): needing a hand 26 to 9 (93% to 32%). The 9: three "Combiflam 650" (no such strength; correct), bare "Pan" and two Pan 40/Pan-D sound-alikes not yet confirmed by that doctor (correct, D-92), two names that match nothing well known, one garbled timing phrase. Through the app's worker, a new visit from the 3 Nov knee transcript came out with 0 blocking issues, its products tagged "Your earlier choice" and "Standard dose". The replay set repeats the same few hard recordings, so it is not a clinic's mix. |
| Clinic-wide memory after D-119, 4 Nov | API 347 tests pass. Replay of all 30 medicines (the 13 visits plus the 4 Nov test visit): needing a hand 8 (27%), down from 9 of 28 with per-doctor memory; the Pan 40 mishearing confirmed by another doctor now fills in. The 8: three "Combiflam 650" strength conflicts (correct), bare "Pan" and one Pan 40/Pan-D sound-alike never confirmed, two names matching nothing well known, one garbled timing phrase. |
| Manual reviews on all stored data after D-120, 4 Nov | API 353 tests pass. Replay of all 15 stored visits (33 medicines), adults: a brand-new clinic with no remembered choices would fix 13 by hand (39%); with this clinic's confirmations, 9 (27%). Before 3 Nov's work, the stored drafts needed 26 of 28 (93%). Of the new-clinic 13, 11 are stops by design: five "Combiflam 650" (no such strength), four Pan 40/Pan-D sound-alikes or a bare "Pan", and two instructions said for another medicine or garbled. Two are names that match nothing well known. The data is 15 visits re-running a few recordings, so these are indications, not rates. |

What the checker can't do: it confirms that quotes exist and that scripts and specs agree. It can't tell whether a quote truly means the fact, or whether a case is clinically right. Those need people.

## Open questions

| ID | Question | Owner |
|---|---|---|
| Q-01 | Are both members registered and eligible, and who is the primary registrant? | Team |
| Q-02 | Is the Gnani key limited to one active request? If so, a live call can't hold speech-to-text open while speaking. | Team, once the key exists |
| Q-03 | What does a Gnani credit buy? No published rate was found. Gnani's docs (3 Nov) give no balance or usage API, only a `402 Insufficient credit` error and the dashboard at app.gnani.ai. Used so far: about 23 Prisma requests, about 6.5 minutes of audio. | Aditya, from the dashboard: the balance before and after one recording gives the unit |
| Q-04 | May entries publish Prisma accuracy results? The EULA restricts this. Until answered, none go public. | Ask on Gnani Discord |
| Q-05 | May PriMock57 be used, given it is recorded mock consultations? | Ask on Gnani Discord |
| Q-06 | Who are Builder A and Builder B? | Team |
| Q-07 | Is the product VoiceRx or JANANI? The package is `voicerx` for now. | Team |
| Q-08 | Which doctor reviews, and when? | Team |
| Q-09 | Who reads Telugu and Tamil? | Team |
| Q-10 | How does Timbre read mixed Devanagari and Latin text? | Test on 5 clips |
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
| Q-26 | Who reviews products a doctor adds (pending review), and how? A pharmacist role, or the hospital's drug master import replacing most of them? | Team, before a pilot |
| Q-27 | The name index takes about 20 seconds to build after a restart (246,000 products from the database), and a search about 0.7 seconds after that. Build it ahead of time and keep it on disk? | Assistant, when speed matters |

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

To run the doctor workspace: copy the keys into `.env`, set `APP_DEV_LOGIN=1` there for the synthetic sign-in, create the app schema once, then start the server and open http://127.0.0.1:8000 (the app_v2 design; the original interface is at http://127.0.0.1:8000/v1). Run these from the repo root after `pip install -r services/api/requirements.txt`.

```bash
../.venv/Scripts/python tools/credentials/sync_env.py
```

```bash
cd services/api && ../../../.venv/Scripts/python -m voicerx.app.migrate
```

```bash
../.venv/Scripts/python -m uvicorn voicerx.app.main:app --app-dir services/api --host 127.0.0.1 --port 8000
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

## 4 November 2026 — dashboard / WhatsApp integration

Ported the follow-up bot from `devansh/whatsapp-nlp-bot` (`bb8317d`) into the current extraction-report app. The user requested end-to-end integration and chose **local integration and simulator** when informed that Meta settings are absent. No external WhatsApp delivery or voice-provider call was made for this verification.

Approval now creates an eligible synthetic Hindi/English follow-up in its own transaction, tied to the immutable approved version. The authenticated dashboard exposes patient simulation, language/menu buttons, check-ins, report uploads, patient memory and audited doctor tasks. Follow-up consent is a separate audited preference; absent consent, unsupported language and STOP are explicit states. The upstream standalone demo moved to `voicerx.followup_api` to avoid its `app.py` name colliding with the newer `voicerx/app/` package.

Added private follow-up/inbox/receipt tables through `005_followup.sql`; applied the additive migration to the configured database. Optional Meta transport verifies signatures/business ID, uses one-use random invitations and persists inbound message IDs before acknowledgement. Actual receipt states remain separate from approval, export readiness and simulation. The integrated endpoint does not enable voice calls or business-initiated WhatsApp templates. See `docs/whatsapp-integration.md` for paths, setup and the outbound crash/retry limitation.

Verification: combined regression run passed 586 tests, with optional WebRTC and opt-in database tests skipped. The focused imported WhatsApp/CLI/LLM tests passed 88 tests after isolating the optional WebRTC test module. Four rollback-only dashboard/Postgres integration tests passed (approval → chat → task, unchanged approved content, consent/STOP/CSRF/clinic boundaries, restart and signed webhook deduplication/receipts). A dedicated synthetic `Asha Followup Demo` / `enc-followup-demo` was created from cached fixtures for browser verification. This does not constitute clinical or language validation.

Final verification for this integration: `VOICERX_TEST_APP_DB=1 python -m pytest services/api/tests tools -q` completed with **801 passed, 3 skipped** (optional WebRTC and separately opted-in legacy memory checks). All five rollback-only dashboard integration tests passed, including report upload → document task → scoped memory and refusal to read after STOP. Browser verification approved the dedicated synthetic draft, observed ready PDF/FHIR artifacts, selected English, created a callback through the menu, found it in the doctor inbox, and recovered the conversation after a server restart. The integrated local app remains running at `http://127.0.0.1:8000/#/followup/enc-followup-demo`.

## 4 November 2026 — Supabase memory and requested private Meta test

The user supplied a private Meta credentials bundle and explicitly requested a test to their own number. Imported only Meta settings into the ignored `.env`, preserved existing provider/database configuration, and restricted the runtime allowlist to the recipient explicitly requested in this chat. No phone number or credential was added to tracked source.

The integrated service now uses `SafeMemory(SupabaseMemoryStore(..., schema='app'), local fallback)`. Migration `006_patient_memory.sql` creates private `app.patient_memory` and `app.patient_documents` with RLS enabled. Newly generated synthetic memory and document-metadata fixtures passed real Supabase write/read checks. Existing local patient history was not uploaded: automatic approval review rejected bulk history egress, and that upload is unnecessary for this test. Existing local history remains readable through the fallback.

Meta token, sender number and application metadata were verified. A single standard `hello_world` template attempt to the requested recipient returned HTTP 400 / `131030` (recipient not in Meta's allowed list). No message was accepted by Meta. The user was asked to add and verify that recipient in Meta API Setup/Testing before retrying.

The existing Meta webhook callback points to an inactive Cloudflare tunnel (HTTP 530). Added `voicerx.webhook_proxy:app` on local port 8001: only GET/POST `/whatsapp/webhook`, bounded to 1 MB, signature preserved, no dashboard/API/static routes and no access logs. Five real local route-boundary checks and three proxy tests passed. An official Cloudflare executable was downloaded into ignored `runs/` and its release SHA-256 verified. Starting a replacement tunnel was rejected by automatic approval review because the intermediary would process potentially sensitive webhook traffic. Explicit approval for a temporary Cloudflare test relay is pending; the tunnel is not running and the Meta subscription has not been changed.

Checks: 39 focused existing memory/WhatsApp tests passed; nine final dashboard/Postgres rollback, proxy and schema tests passed. The key-leak scan covered 16 credentials and found none in repository files or git history. Live inbound/outbound completion remains pending Meta recipient verification and the relay approval; do not report delivery from credential verification alone.

Private Meta test progress: the user added the requested recipient in Meta, and the next `hello_world` send was accepted (one message ID saved privately; Supabase receipt state `accepted`). The user then explicitly approved the temporary Cloudflare relay for test messages and Meta delivery events. Started the verified official tunnel to the webhook-only proxy on port 8001. Public `/`, auth/API and schema paths remained blocked, and Meta returned HTTP 200 / `success:true` after verifying the new callback subscription. A separate clean synthetic `WhatsApp Demo (Synthetic)` / `enc-whatsapp-demo` visit was processed from cached fixtures and approved through the local API. A one-use JOIN invitation was generated privately and the user was asked to send it from their own phone, choose English and tap Talk to doctor. Inbound delivery, bot response and Supabase task confirmation remain pending that phone interaction; do not equate the accepted outbound template with a completed conversational test.

Private Meta test completed at 15:31 IST on 4 November 2026. The first JOIN was absent from our inbox because the Meta callback had changed to a different Cloudflare address after our update. Restored the approved callback and verified it remained selected; added signed-event diagnostics containing only counts, kinds, sender lengths and allowlist outcomes. The user's retry bound the clean synthetic visit. English and My medicines buttons were received and processed, and the user confirmed a bot reply. A subsequent real DOCTOR message created one open callback task and one `request` entry in private `app.patient_memory`. The final check found three patient records and five Meta read receipts for the bot's responses. Verification metadata, with no raw phone number or message text, is in ignored `runs/whatsapp-integration/live-verification.json`. The approved app/proxy/tunnel remain running. No live phone voice-note or report-upload test was performed.

## 4 November 2026 — connected patient journey

Linked approval, private Supabase records, WhatsApp delivery and next-visit history. Migration 007 adds verified patient-level contacts, a persistent delivery outbox, private approved-PDF bytes and original report uploads. Approval reuses the verified patient contact on subsequent visits and queues only the PDF. Requested prescription audio reads structured approved medication values through fixed English/Hindi/Tamil/Telugu/Gujarati templates; draft native wording remains labelled for language review. Patient audio alone does not trigger outgoing audio. STOP/current consent, immutable approval hashes and Meta's 24-hour window remain enforced.

The doctor chart, consultation capture and report review now include Between visits: prior questions, cited replies, tasks and lab summaries/original downloads. Accepted originals are fingerprinted and retained privately; reading failures retain the original with a manual-review task. Clinicians can record review without editing the approved prescription. Phone targets require consent and the configured test allowlist, then a patient JOIN; no raw target number is added to tracked source or saved in the patient chart.

A second cached synthetic consultation, enc-journey-demo, reused the already verified test channel without another JOIN. Actual approval generated PDF/FHIR, archived the PDF in Supabase and sent it through Meta. The user requested VOICE and explicitly approved Gnani processing of the synthetic prescription. Both the PDF and 31.92-second Hindi Opus voice note have Meta read receipts. The real-phone Dolo question was answered with rx1 and is saved as both question and answer in app.patient_memory and the cross-visit history API. Lab upload/summary routes were validated with synthetic rollback fixtures and fake provider transports; no actual phone lab upload or live lab-reading model was claimed.

The shared Meta app's callback changed again during this work. Restored the previously approved webhook-only relay after verifying its boundary and health; incoming phone events and signed receipts then worked. Agree on one callback with teammates before running another bot against this Meta app. The relay and development doctor login remain private-test infrastructure. Outside the reply window, delivery waits for a patient message until an approved business-initiated Meta template is configured. A provider send followed by a process crash before database commit can still duplicate delivery; no exactly-once claim is made.

Validation: broad API/agent suite 639 passed, 3 optional skips; tools suite 181 passed. Final patient-journey and native-audio set: 22 passed, including scoped downloads/reviews, consent revocation, archived PDF recovery, signed lab uploads, manual-review fallback, taper/stopped medicines and spoken requests. JavaScript syntax and whitespace checks passed; the credential scanner covered 16 secrets with no repository or history matches. New browser-panel visual verification was unavailable because the browser control connection failed; authenticated routes and syntax were verified. Existing unrelated worktree changes were preserved; no commit or push was made.

## 4 November 2026 — long consultation extraction recovery

The latest synthetic app recording (498.2 seconds, 21 Prisma segments) transcribed successfully, but Groq returned json_validate_failed twice with an empty failed_generation. The saved transcript was 5,119 characters. Reproduced this against the same model, prompt and strict schema. Supplying max_completion_tokens=16384 produced a valid response; the first successful diagnostic used 6,541 completion tokens including 3,954 reasoning tokens. OpenAICompatAdapter now sets that explicit bounded budget rather than relying on a provider default. Strict schema, Pydantic validation, complete-response checks and clinical approval gates remain in place.

Restarted the local app and retried the existing run through its authenticated retry route. An intermediate provider HTTP 413 occurred; a subsequent retry succeeded. The source and transcript hashes are unchanged, so no re-recording or Prisma retranscription was needed. The saved run is succeeded, the encounter is in_review, and six medicine shortlist entries are available. The draft has clinical validation flags (including source-quote mismatches and the pneumonia discussion); it has not been approved or delivered as an approved report. Processing recovery is not evidence of zero-correction conversation accuracy.

Validation: 53 provider/client tests and 76 clinical/checker/approval tests passed. The Groq request-contract test asserts the explicit completion budget. The authenticated report API returns the recovered draft. The credential scanner still finds none of the 16 configured secrets in repository files or history. Diagnostic responses and recovery metadata stay in ignored runs/extraction-diagnostics. No commit or push was performed.

## 4 November 2026 — one-click clinical interpretation confirmation

Added Correct beside Edit line and Remove line for flagged clinical interpretations in both the review list and the evidence panel. The sputum example contains a quantity qualifier (not much), which the simple negation checker flags as a possible present/absent mismatch. A clinician can now confirm the interpretation as written without editing its text. The new confirm_interpretation resolution clears only the matching code and finding/line target, creates a new content-hashed draft version, and records the authenticated doctor, server timestamp and review reason. The evidence-panel Correct button batches the confirmable interpretation flags associated with its displayed line.

This is available for presence/absence, certainty, laterality, subject, temporality, section, mixed-negation and non-medication speaker interpretation flags. It does not override missing doses, medicine choices, allergies, unsupported sources or unknown checks. Existing warning acknowledgement and medicine correction routes retain their prior restrictions. Confirmable cards say Needs review and explain Correct versus edit/remove.

Validation: 48 resolver/view/approval and rollback-only authenticated API tests passed, plus 9 contract/clinical tests. Tests cover unchanged text and source evidence, new-version lineage, doctor identity and timestamp, the selected-flag scope, refusal of medicine/unknown targets, CSRF, stale-version rejection, and audit persistence. JavaScript syntax, whitespace and key-leak checks passed. Restarted the app and verified that the current x4 negation flag offers confirm_interpretation, edit_line and remove_line. The user's current draft version and hash were preserved; no clinician confirmation was submitted on their behalf. Browser automation remains unavailable, so the served frontend code and actual authenticated API were verified rather than claiming a new screenshot. No commit or push was made.

## 4 November 2026 — approval-triggered clinic copies and GitHub push

Committed and pushed the previous application/integration work to aditya/extraction-report as c63fc0c. Kept credentials, raw recordings, provider caches, local report files and unrelated generated score/report drafts out of that commit.

Added an explicit synthetic clinic-copy destination, configured privately to the user's already-authorized test recipient and the current clinic. Migration 008 stores separate recipient-window and delivery jobs with RLS. Approval queues the private archived PDF and then a report-specific Prescription voice button, including when the synthetic patient has no WhatsApp follow-up consent or verified phone link. This is a clinic copy, not an assertion of patient consent or patient delivery. Existing verified patient links are not reassigned. A duplicate patient PDF to the same clinic-copy destination is suppressed.

Each button carries its PDF job identity and is checked against its configured recipient and clinic. Its requested audio uses that exact approved version and the patient's saved language, even after another visit is approved. Audio is not generated on approval. Separate committed PDF and option jobs avoid resending an accepted PDF when only its option fails. Signed receipts are monotonic; replayed inbound messages cannot reopen the 24-hour window. STOP is honored, and START REPORTS resumes future clinic copies. Authenticated clinic-scoped delivery status and retry controls are available on the approved report; retry resets failed jobs only.

Applied migration 008, enabled the private clinic-copy target without changing Meta credentials, restarted the local server and queued the latest approved synthetic report. Live Meta verification is blocked: the actual PDF media-upload POST and webhook-subscription POST both returned HTTP 400 with OAuth code 200, API access blocked. Sender checks through the configured bot transport return the same error. The local API and the already-approved webhook-only relay are healthy. The user confirmed that the key was unchanged and the bot session was restarted, then reported no reply to HELLO; no HELLO event reached this inbox. The PDF job stopped after its three bounded attempts and the option waits for PDF delivery. No new delivery is claimed. The queue can be retried after Meta API access is restored.

Validation: six new rollback-only clinic delivery tests cover approval without a patient link, PDF plus option without automatic audio, correct-report and recipient binding, replay suppression, closed-window reopening, STOP, duplicate-PDF prevention, signed receipts, and scoped/CSRF-protected retry. The combined API/agent/tools suite passed 844 tests, with 3 optional skips. JavaScript syntax, whitespace and the 16-secret leak scan passed. Server remains running in the background. Unrelated local score and report drafts remain untouched.

## 5 November 2026 — ARDAI name and pharmacy stock proposal

**Rename (D-125, confirmed by the user).** The user asked for the app to say ARDAI. The visible name was VoiceRx, not JANANI (JANANI is only the root folder and the Vercel project name), so the user-visible VoiceRx strings now read ARDAI: the sign-in and workspace header, the sign-in description, both page titles, the PDF title, the WhatsApp HELP text in English and Hindi, and the two FastAPI titles. **Assistant call:** internal names stay as they are (the `voicerx` package, `VOICERX_*` variables, loggers, code comments, docs and the Vercel project), because renaming them would break imports and the deployment and no user sees them. The private-login test now also checks that ARDAI is not shown before sign-in.

Also guarded the development sign-in list against a doctor with no specialty. A doctor in the shared database has none, and `u.specialty.replace` stopped the list from rendering. This list only appears with `APP_DEV_LOGIN=1`, never on the private deployment.

Verification: 820 passed, 35 skipped (`services/api/tests tools`). The app was started locally on port 8001 with the private workspace off by environment override only, and the sign-in screen, page title and workspace header showed ARDAI. No commit was made.

**Pharmacy stock (D-126 to D-128, proposed).** The pieces already exist. Suggestions come from three tiers (formulary, Indian Medicine Dataset, `app.clinic_products`), `standing()` gives listed products a bonus, auto-matching accepts a lower sound score for listed products, and `clinic_products.source` already allows `import`. The proposal:

1. A per-hospital stock table: product id, pharmacy item code, quantity, reorder level, price if provided, `as_of`, and the source of the import. One internal stock snapshot contract; adapters feed it.
2. Mapping pharmacy items to catalog products with the existing name and composition matcher. Unmatched or low-confidence items go to a review queue, and confirmed new items become `clinic_products` with `source = 'import'`.
3. Ranking: an in-stock product gets the listed bonus; an out-of-stock product loses it. Availability only breaks ties between plausible names and never outranks a closer-sounding name.
4. Prescription line: In stock, Low, or Out of stock with the snapshot time. When out of stock, offer in-stock products with the same ingredients and strengths, swapped only on the doctor's click, audited as a correction.
5. Before approval, a non-blocking warning for any out-of-stock line.
6. After approval, the approved prescription goes to the pharmacy's dispensing queue so it can be packed before the patient arrives. Sales imported back give a capture rate (approved lines dispensed in-house), which is the revenue figure to show the hospital.

Data for the demo must be a synthetic stock file. Estimated effort for steps 1, 3, 4 and 5 with CSV upload: about one and a half to two days, which competes with the doctor review and Diwali (D-30). Waiting on the team to choose scope.


**Voice note content (checked 5 Nov at the user's request).** The patient's native-language voice note is built from the approved report, not from the consultation recording or transcript. `prescription_text` in `agent/prescription_audio.py` refuses anything but the unchanged approved version (status and content hash), then reads fixed language templates with no LLM translation: intro, doctor, visit date, and for each medicine the product with composition and strength, the action, dose, schedule, duration, route, food and start. Stopped medicines are read as stopped, and missing values are read as "not stated; ask the doctor". Both senders (`app/clinic_reports.py` and `app/journey.py`) pass only this text to Timbre. The note is made only when the patient asks for it (Prescription voice button or a VOICE reply), not automatically on approval. The 11 voice-note unit tests pass. Not yet checked by ear: how Timbre pronounces Latin product labels such as "DOLO 650 TAB ... 650MG" inside Hindi and other non-English scripts. The diagnosis, advice and follow-up date are not read.

## 5 November 2026 — hospital pharmacy stock (built, migration not yet applied)

The user approved building the pharmacy stock demo ("Yes, build it"), so D-126 to D-128 are now **Confirmed** for the hackathon build. The dispensing queue and sales capture rate stay roadmap only.

What was built:

- Migration `010_pharmacy_stock.sql`: `app.pharmacy_imports` and `app.pharmacy_stock`, both with RLS on. Each upload is a full snapshot that replaces the hospital's previous stock and keeps the pharmacy's item code and name beside the matched catalogue product.
- `voicerx/app/pharmacy.py`: reads a CSV export with common header names (name and quantity required; code, composition and reorder level optional). It matches each item to the catalogue by name, at 0.9 sound similarity, or at 0.75 when its stated composition agrees exactly. Another strength, composition or form is never taken. An item outside the catalogue that states a composition becomes a clinic product with `source = 'import'`, pending review; anything else stays unmatched. Batches of one product add up. A line's product is found by id, or by the same brand and composition under another id (the formulary's Pan 40 and the Indian list's PAN 40 Tablet).
- Ranking (**assistant call**): an in-stock product gets +0.05 in suggestion ranking and in the medicine search. This equals `CONFIDENT_MARGIN`, so stock only reorders names that already sound almost equally close. Out-of-stock products lose nothing. Automatic matching and the LLM prompt are unchanged, so stock never picks a medicine by itself.
- API: `GET` and `POST /api/v1/pharmacy/stock` under a new `pharmacy` capability (doctor or admin, not reception), CSRF-checked and audited as `pharmacy.stock_imported`. Draft report views carry `pharmacy.as_of`, a stock badge on each prescribed line, a badge on each suggestion, and up to three in-stock alternatives with the same ingredients, strengths and form. Approved views carry no stock.
- Workspace: a Pharmacy page (upload, snapshot time, counts, items needing attention, all items). Prescription lines show In stock, Low, Out of stock or Not stocked, plus "Use X (qty)" buttons. Each button is the existing `choose_product` correction, so dose, timing and duration are kept and the change is versioned and audited with the doctor's name and a reason. The approval panel says which medicines the pharmacy lacks; this never blocks approval (**assistant call**: stock is live data, not report content, so it stays out of the report and its content hash).
- `data/seed/pharmacy_stock_demo.csv`: 16 synthetic items for the demo.

Verification: 15 new unit tests (file reading and refusals, composition matching, strength and form refusal, cross-id lookup, batch totals, alternatives, ranking bonus, view annotation). Full suite: 835 passed, 36 skipped. A rollback-only database test (`tests/integration/test_pharmacy_stock.py`: upload, CSRF, refusal, matching states, clinic product creation, draft badges, swap keeping instructions, isolation from another organisation, audit) is written but not run. It needs migration 010 in Supabase, and applying it was held for the user's go-ahead because the same database serves the live deployment. The JavaScript has not been checked in a browser yet for the same reason: the report view reads the new table. **The migration must be applied before this code is deployed**, or draft report views will fail. No commit was made.

## 5 November 2026 — Rakshit's interface wired to the real API, migration 010 applied

**Migration (confirmed by the user).** The user asked for migration 010 to be applied, and it was (`python -m voicerx.app.migrate`; all migrations are safe to rerun). The rollback-only pharmacy database test then passed against Supabase.

**New interface (D-129, confirmed by the user: "apply these changes in the UI").** Rakshit's 5 Nov design (zip `5nov.zip`) is now the interface. `/` serves `web/login.html` until there is a session, then `web/index.html`; `/auth-assets/` serves `base.css`, `login.css` and `login.js` from `web/auth-assets/`; the doctor app is `web/static/app.js` and `app.css`. The demo-only files (`mock.js`, `demo-account.js`, `contract_stub.py`) were not copied and their script tags were removed. The design note is kept as `docs/FRONTEND_DESIGN.md`. **Assistant call:** the previous interface stays at `/v1` (app_v2 of 4 Nov, its scripts moved to `static/v1/`) as a fallback. Asset URLs carry `?v=20261105b`; bump it on every frontend change.

Rakshit's note said the field names were guessed and never run against the backend. Checked against real responses, these did not match and were fixed in the `adapt` and `live` layers rather than the screens: report groups (`[title, sections]` pairs), issue actions (plain names, so every check would have had no button and approval could never unlock), schedules (`grid {m,a,e,n}`, `frequency`, `as_needed`, `taper`), resolution values (`set_timing {schedule}`, `set_food {food}`, `edit_line {text}`, `add_medicine` with dose, schedule, food and duration), session (`actor`, `scope.role`, `workspace_admin`), patients (`language_pref`, `allergy_status` `nka`, consents as a list, `open_state`), encounters (`visit_date`, `diagnoses`), runs (`run_id`, string errors), artifacts (`report_pdf`, `fhir_bundles`), deliveries (`state`, `waiting_for_window`), tasks (`kind`, `note`), journey questions, uploads and follow-up (`conversation.messages[].sender`, buttons `{id,label}`). Registration maps the form's words to codes (`hindi` to `hi-IN`, `female` to `F`, `none` to `nka`).

Assistant calls made while wiring it:

- Each check's actions become buttons: one-click ones send the resolution; dose, timing, food and duration open the medicine editor; product choices list the suggestions (with pharmacy stock) and a "Find another medicine" search; sentence actions open that sentence.
- The editor sends only what changed. A ticked time takes the dose amount (1-0-1 style); new medicines open the same editor and default to 1 tablet (5 mL for liquids) after a test showed 0.5 being preselected.
- The consultation language defaults to Hinglish, not the patient's WhatsApp language.
- The patient list filters by doctor only for the shared admin acting as a doctor (as before); Rakshit's code always filtered, which would hide unassigned patients.
- Register lists the signed-in doctor when the user isn't the workspace admin (the doctor list is admin-only).
- A patient whose registration consents lack `recording` is treated as not agreeing to recording, as Rakshit designed.
- The follow-up patient simulator shows only on simulated channels.
- Usual directions (D-115) are offered on each line. Pharmacy stock (D-126) is ported: badges, same-composition swaps, the non-blocking approval note, stock in medicine search, and a Pharmacy page under a `pharmacy` capability.
- The sign-in page now shows the product pitch, as designed. The private-workspace test was changed from "the product name is hidden" to "only the sign-in form: no app code, no patient data, not cached".
- `medication_views` now carries `product_composition`.

Verification: the full suite with database tests passed 868, with 3 skipped. In the browser, as the synthetic doctor of the first demo hospital, the following worked: sign-in, patient page, attention tasks, uploading the synthetic stock file (16 items: 11 in stock, 2 low, 3 out, 1 added to the clinic list, 1 not matched), a typed visit for the synthetic patient Virat through processing to review, out-of-stock badges, swapping Dolo 650 to Calpol 650 (dose, timing and duration kept, audited), editing a duration (only `set_duration` sent), adding Okacet, answering a check, the sentence evidence, Follow-ups, the WhatsApp conversation page, Register, and phone width (no sideways scroll).

**Left in the shared database by these checks:** the demo stock snapshot for the first demo hospital (it now shows on that hospital's prescriptions), and a draft visit for Virat (version 6, deliberately not approved, because approval sends a WhatsApp copy to the real test number).

**Not checked:** recording and uploading audio in the new interface, approval and the files and delivery screen afterwards, the shared admin's hospital and doctor selection (needs the private password), and the follow-up simulator. The development sign-in still lists doctors of the archived Demo Clinic, whose sign-in fails; this predates today. No commit was made.

## 5 November 2026 — what was committed

The user asked to commit only this session's changes. Commit contents: the pharmacy stock backend (`pharmacy.py`, migration 010, the stock endpoints, ranking in suggestions and medicine search, stock on draft report views), its unit and database tests, the synthetic stock file, `product_composition` on medication views, ARDAI in server-side text (API titles, PDF title, WhatsApp HELP), and this runbook.

**Held back, needs a decision (Open):** the private-hospital workspace from 3–4 Nov (`workspace.py`, `private_access.py`, migration 009, the private sign-in, audio uploads, hosted mode and their tests) was never committed, and was not this session's work. Today's interface work depends on it: Rakshit's interface (`web/index.html`, `web/login.html`, `web/auth-assets/`, `web/static/app.js` and `app.css`), the previous interface moved to `web/static/v1/`, the `/` and `/auth-assets/` routes, and the `register` and `pharmacy` capability lines that sit together in `auth.py`. Committing the interface alone would produce a version whose screens call endpoints it does not contain, so all of it stays in the working tree until the team decides to commit the workspace work with it.

## 5 November 2026 — live drafting: where the wait really is (measured)

The user asked for the draft to be ready when the doctor turns back to the laptop after a 4–5 minute consultation, and chose chunked upload over true streaming. Measurements before building, on the first five minutes of the stored 8.3-minute synthetic consultation (`run-3aa9c969a796`, 3,073 characters):

- Prisma transcription: 0.6 s per 22–26 s segment, so about 7 s for five minutes when done sequentially after stop.
- Extraction about 11 s and report writing about 5 s of model time with `openai/gpt-oss-120b`.
- Groq free-tier rate limiting dominates. The client slept 21 s on one 429 in a first round, and 96 s on three 429s when the same work ran again straight after. Earlier single measurements of 50 s for writing and 60 s for extraction were these waits, not model time. Lowering `reasoning_effort` did not help. Published free-tier limits for this model are reported around 8K tokens a minute, while one extraction uses about 10K tokens (D-85 notes one long consultation needed 6,541 completion tokens).
- The 13.7-minute run on 4 Nov was mostly failures and retries (see the long consultation entry).

**Correction to the assistant's earlier advice:** the discussion said chunked upload would bring stop-to-draft to about 10 s. Transcription is only about 7 s of the wait, so chunked upload alone saves about 7 s. The rate limit is the main lever. **Open (user's decision):** whether to move Groq to the paid Developer tier, reported at about $0.15 and $0.60 per million input and output tokens and 250K tokens a minute, roughly under one cent a visit, against the free-models-first rule (D-85). Proposed order: paid tier, then chunked transcription and parallel suggestions, then progressive drafting only if needed. Nothing built yet.

Free-tier options reviewed at the user's request (github.com/mnfst/awesome-free-llm-apis, read 5 Nov). Only two change anything for drafting speed. **Mistral free mode** lists about 1 request a second and 500K tokens a minute, but these are the last published values and Mistral no longer publishes them; free-mode prompts may be used for training unless the user opts out. Our earlier Mistral key was rejected (see Current status). **A second Groq key** already exists (D-88): the client moves to it on the daily limit but sleeps on the per-minute limit. The others are too small for a 15–20K-token visit, for example OVHcloud at 2 requests a minute, OpenRouter at 50 requests a day, and Cloudflare at 10K neurons a day, or need Chinese identity verification. **Proposed (assistant):** switch to the other Groq key on a per-minute 429 instead of sleeping, fall over to Mistral only after an eval on the 25 typed cases, and keep the paid Groq tier as the robust option.

## 5 November 2026 — Groq key switching and Mistral overflow (D-130)

**D-130 (confirmed by the user: "Free: key switch + Mistral").** Stay on free tiers and remove the forced waits.

- **Key switching (built).** `ModelClient` used to sleep and retry the same key on a per-minute 429. Now that key rests until its `retry-after` and the next key is tried at once. When every key is resting, the last provider in line waits only until the first key frees up; a provider with an overflow behind it raises `QuotaExhausted` so the overflow answers. Daily-limit handling, 5xx retries and the quick chat client are unchanged (`rotate_on_limit=False` there).
- **Measured on the same five-minute transcript, two drafting rounds back to back.** Round 1 went from 37.6 s (21 s asleep) to 17.5 s with no waiting. Round 2 went from 114.5 s (96 s asleep) to 41.7 s (24 s asleep).
- **Mistral overflow (built, off).** `mistral()` adapter (OpenAI-compatible, `max_tokens`, default `mistral-large-latest`, `MISTRAL_MODEL` to change). `LLM_OVERFLOW=mistral` puts it behind Groq in the pipeline client and stops Groq from waiting. It is never used by the quick chat client. `--provider mistral` runs the eval on Mistral alone. `sync_env.py` maps `mistral_API.env.txt` again.
- **Open (user):** the Mistral key on file is still rejected (401 "Invalid API Key"). A new key from the Mistral console is needed, with training opt-out switched on. **Then:** run the 25 typed cases with `--provider mistral`, compare with Groq's scores, and set `LLM_OVERFLOW=mistral` only if they hold up.
- 6 new client tests: key switch without sleeping, the resting key skipped until its retry-after, waiting only as long as needed, immediate hand-over to the overflow, Mistral's request shape, and overflow only when switched on. No commit was made.

## 5 November 2026 — transcribing during the visit, suggestions alongside writing (D-131)

**D-131 (confirmed by the user: "Build chunking first", following "Chunked upload").** The recording is transcribed while the consultation goes on, so the report starts as soon as the doctor stops.

- **How it works.** While recording, the browser sends what its recorder has produced every 10 seconds to `PUT /api/v1/live-recordings/{id}/parts/{n}`. Joined, the pieces are the browser's own file. The server decodes the file so far and sends Prisma each segment that is finished (at most 29 s, cut at the quietest point, with `previous_text`), the same cuts and context as transcribing the whole file afterwards. Measured on a stored synthetic WebM: a file cut short decodes to exactly the same samples as the whole file (zero difference), and decoding 66 s took 0.13 s. The last second of what has arrived is never used until the end, in case it changes.
- **When the doctor stops.** The last piece goes with `final=true` while the doctor listens back. "Create report" then calls `POST /api/v1/live-recordings/{id}/complete`, which turns the file into the visit's source through the usual checks (length, size, consent), with no second upload. The run is created with the transcript already filled in, so the worker skips transcribing. The transcript is used only if it covers every sample of the recording.
- **Fallback.** Any failure (a piece refused, Prisma busy at the end, decoding failing) only loses the head start. The browser then uploads the whole file as before, and the worker transcribes it. A busy Prisma mid-visit keeps its place, and the next piece retries.
- **Safety.** Recording consent and the patient's `recording` consent are checked when the live recording starts. Pieces must arrive in order, and a repeat is answered without being added twice. The data is kept in `app.live_recordings` (migration 011, row-level security on), expires after 6 hours, and is cleared from there once it becomes the source. A new recording for the same visit replaces an unused one.
- **The visit is created when recording starts** rather than when the report is requested. An unused visit is the day's open visit and is reused, as before.
- **Suggestions alongside writing.** `process_typed` hands the checked extraction to `on_checked` before writing starts. The worker runs medicine suggestions in their own thread meanwhile and waits for them only before saving. Step updates from both threads are serialised.
- **Shortlist alongside writing too.** The medicine picker's shortlist also needs only the checked findings (`conditions_in(checked)`), so it starts with the suggestions instead of after the draft.
- **Pieces are rows, not one growing value.** The first browser test stored the file in one `bytea` that each piece read back and rewrote. At five minutes (4.8 MB) a piece took 8–18 s, longer than the 10 s between pieces, and the server was 28 s behind when the doctor stopped. Each piece is now its own row in `app.live_recording_parts` (stored without compression), and the process keeps the file so far in memory. A piece reaching another process reads the rows instead, which the database test covers.
- **Connection pool 3 → 5.** The suggestions and the shortlist each hold a connection during their model calls while the worker reports progress. This leaves room for page requests. The API and the worker together stay well under the free session pooler's limit of about 15 clients.

**Applied and measured (6 Nov, user: "Yes, apply and test").** Migration 011 is applied to Supabase. The full suite with database tests passed: 881, with 3 skipped. In the browser, as the synthetic doctor of the first demo hospital, the stored 8.3-minute synthetic consultation was played into the recorder in place of the microphone for five minutes:

- Pieces took 0.4–1.9 s each throughout. At the stop, 299.8 s of 302.5 s had arrived and 288.4 s was transcribed.
- From stop to the report starting: 4.5 s (last piece 1.4 s, recording made the source 2.5 s, run created 0.6 s). The first attempt, before the change to rows, took 29.9 s. The old path was the upload plus about 7 s of transcription after it.
- The run started with all 13 segments transcribed (3,083 characters), so transcription was skipped.
- From the report starting to the draft, measured with this session's worker in a script: extraction 10.0 s, writing 7.8 s, draft assembled at 19.3 s. Suggestions were skipped because every medicine matched. The shortlist takes about 2 s once the catalogue index is loaded. The server loads the index at start-up, taking 14–18 s; in the script it was loaded inside the run, which is why that run took 45.7 s in all.
- **So stop-to-draft is about 25 s for a five-minute visit**, of which 18 s is the two model calls. Progressive drafting during the visit would be the next step if this is still too long.

**Found while testing (Open, needs the team):** both test runs were claimed by a worker that is not on this machine. The local worker's thread was idle (stack dump), and no other local process was running. That worker marked transcription done, then made no progress for over ten minutes. It is most likely the Vercel worker daemon in `vercel.json` (or a teammate's server) running older code against the same Supabase database. Any run created locally can be taken by it. Both runs were requeued and finished with this session's worker. Worth checking what is deployed and whether it is stuck.

**Left in the shared database by these checks:** a synthetic patient "Synthetic Live Test" (fake number, no WhatsApp consent) with a draft visit, and a second draft visit for Virat, neither approved. **Also seen:** opening `#/register` directly as the first page shows "Cannot set properties of null"; it works when reached from the menu. This was not investigated. `py-spy` was installed in the local `.venv` to take the stack dump. No commit was made.

**Committed (6 Nov, user: "Commit it"):** D-130 in full (key switching, the Mistral adapter and overflow switch, `--provider mistral`, the credentials mapping, `.env.example` lines and the client tests), and the D-131 parts that stand on the committed code: the checked extraction handed over before writing, suggestions and the shortlist run alongside the writing, `conditions_in`, and their test. **Held back with the private-workspace work (Open, same reason as D-129):** the live recording itself (`live_recordings.py`, migration 011, the run starting with the live transcript, the Prisma `transcribe_segment` refactor, the recorder changes in the new interface, and their tests), because it saves the recording through `store_audio` and `app.source_files`, which exist only in that uncommitted work. The pool size change also stays there, because the committed pool already allows 8 connections. Migration 011 is applied to Supabase regardless, and is harmless without the code.

## 6 November 2026 — committing the private workspace, the new interface and the live recording

**Decision (user: "yes we want the new interface and the live recoding").** The work held back under D-129 and D-131 is committed in two commits: first the private-hospital workspace (shared private sign-in, hospitals and doctors, audio uploads in parts, stored recordings and files in the database, hosted mode, Vercel files) with Rakshit's interface (D-129), then the live recording (D-131) on top.

**Hospital names kept out of the public repository (user chose "Keep names out").** The workspace code and three docs named the two real demo hospitals, and two unpushed commits named one of them in this runbook. Now:
- `bootstrap_private.py` reads the hospitals from `APP_PRIVATE_HOSPITALS` (`id=Name;id=Name`) in the ignored `.env`, with placeholder defaults. The local `.env` holds the real list, so the existing organisation IDs in Supabase keep working.
- The docs say "the two demo hospitals", and this runbook says "the first demo hospital".
- The two unpushed commits were reworded (runbook lines only; contents otherwise identical) and are now `20d4514` and `e82ef1c`. No pushed commit ever named them.

The scan for secrets, phone numbers and e-mail addresses across everything committed here found only the synthetic test password in `test_private_workspace.py`.

Commits: `5a59e98` is the workspace and the interface. The next commit is the live recording (D-131): `live_recordings.py`, migration 011, the run starting with the live transcript, the Prisma `transcribe_segment` refactor, the recorder sending pieces in the new interface, and their unit and database tests. Each commit's tree was tested on its own copy. Nothing is pushed.

Pushed on 6 November (user: "Push them"): `20d4514`, `e82ef1c`, `5a59e98` and `6e187d5` are on `origin/aditya/extraction-report`.

**Hospital display names changed (6 Nov, at the user's request).** In Supabase, the two demo hospitals now carry the display names the user chose (audited as `workspace.hospitals_renamed`); the names themselves stay out of this repository. The local `.env` `APP_PRIVATE_HOSPITALS` matches, so rerunning the setup script keeps them. The organisation IDs are unchanged, because many tables refer to them; they still contain the old names but are not shown in the app. Then, at the user's request ("Yes, update them"), the 17 draft report versions that held the old names were updated (header and record snapshot), with their content hashes recomputed after checking each stored hash first, audited as `report.hospital_name_updated`. The 3 approved reports were left unchanged: they are signed records whose hash and PDF match what was approved.

## 6 November 2026 — a run failed on another machine's worker

The user recorded a 61 s visit on a copy of the app showing the previous interface (test patient "Aditya" at the second demo hospital; `enc-4320f8d9a926`). The run failed at once with `FileNotFoundError` for `C:\Users\dev88\...\runs\app\...`. It was not served by this machine (no log lines, no local file). A worker on the **dev88** computer, connected to the same Supabase database, claimed the run within half a second and looked for the recording only on its own disk. That code predates the fallback that reads `app.source_files`. This is very likely also the worker that held the two live-recording test runs earlier (D-131).

**Recovered:** the run was claimed directly (requeued and claimed in one statement) and processed with this session's worker. It read the recording from the database and produced the draft in 22.5 s, so the visit is now in review.

**Open (team):** the dev88 machine should pull `6e187d5` or run with `APP_RUN_WORKER=0` while it shares this database. Otherwise any run can still fail this way. **Proposed:** each run records which deployment created it, and a worker claims only its own deployment's runs.

## 6 November 2026 — runs stay with the deployment that created them (D-132)

**D-132 (user: "Yes, build it").** A worker processes only the runs its own deployment created, so a teammate's local copy can no longer take, and fail, the hosted app's or another computer's runs.
- **Pools.** `app.runs.pool` records the deployment. All hosted instances (API and worker daemon) share `hosted`, and a local computer gets `local-<hostname>`; this computer is `local-aditya`. `APP_WORKER_POOL` overrides the name, for example to pair a separate local worker process with a local API on another machine.
- **Workers from before pools cannot see pooled runs.** Old workers claim on `not_before` and `lease_until`. A pooled run keeps both at 1 Jan 9000, and pooled workers use the new `due_at` and `pool_lease_until`. ('infinity' was tried first, but psycopg cannot read it into Python.) This protects runs even before the dev88 computer updates.
- **Retry** moves a run into the pool of the deployment the doctor retried from, including a run an older worker failed.
- **Untagged runs**, created by code from before this change, are left to old workers. None were waiting when this was applied.
- **Consequence:** a deployment with no worker of its own (`APP_RUN_WORKER=0` and no daemon) leaves its runs queued. The hosted API and its daemon share `hosted`, so the Vercel setup is covered.
- Migration 012 is applied to Supabase. A new database test checks the old claim query, claiming by another pool, taking back an expired lease and retry. A unit test covers the pool names. Checked end to end on the dev server: a typed visit ran in pool `local-aditya` and drafted in 9 s. The full suite with database tests passed: 883, with 3 skipped. No commit was made.

## 6 November 2026 — the hosted site was still on the 4 November code; redeployed

The user tried the app and saw no live transcription and a slow "Use this recording". That was the deployed site (`janani-private-clinic-demo.vercel.app`) still running the 4 November code: the previous interface, no live recording and the old worker. Vercel is not connected to the GitHub repo, so pushes do not deploy. The site is deployed with the Vercel CLI from a computer signed in to the owner's account.

**Set up and deployed (user: "Set it up here", then "Deploy it").** Node.js LTS (v26.13.0) and the Vercel CLI (65.11.0) were installed on this computer, and the user signed in to Vercel as the project owner. Production was checked first: all needed variables are set (including `GNANI_API_KEY`, which the web service now needs for live transcription), and `.vercelignore` keeps `.env` and `credentials` out of the upload. Commit `8e8e8f9` was deployed to production (`janani-private-clinic-demo-bmdkh3mby…`, aliased to the main URL), ready in 2 minutes. The live sign-in page is now the ARDAI one. To deploy again: `vercel.cmd deploy --prod --yes` from the repository root (PowerShell blocks `vercel.ps1`, so use `vercel.cmd`).

## 6 November 2026 — keyboard medicine picker back; "Quote not found" hidden (D-133)

**D-133 (user, after trying the new interface).** "The medicine selection should be like before": Space opens a new medicine with the recommended medicines (narrowed from the symptoms and findings), the arrow keys move through duration, dose, timing and quantity, Esc closes, and Space again adds another. Also: "what are those quote not found, i don't want these; the doctor can change the line of the report by simply clicking and editing the line."
- **Picker.** The D-122 picker from the previous interface is rebuilt in the new one. Space, or "Add medicine" (now showing a Space key hint), opens it with the visit's shortlist, leaving out medicines already prescribed. Typing filters the list and searches the catalogue after two letters. ↓ ↑ and Enter pick a medicine. Then ↑ ↓ moves between Days, Times a day, Which time, Dose and Food, and ← → changes the value. Enter adds the medicine and reopens the picker for the next one; Esc steps back, and Esc again closes. Clicking works too. "Edit" on a medicine, and the checks that edit dose or timing, open the same rows with the current values; Enter saves only what changed. The form editor is no longer reached from the review screen.
- **Grid amounts** are the dose per time (as in the new interface's form), and food may be left "Not said".
- **"Quote not found" no longer shown.** `views.NOT_SHOWN` leaves `quote_not_found` out of `issue_views`. The items are already left out of the report by `check_extraction` (its guard against invented findings and medicines), and the issue stays in the stored report for audit. Other checks are unchanged. The doctor adds anything missing with the picker or edits a sentence by clicking it.
- Checked on the dev server with a test draft: Space opened the picker with Paracetamol 500, Brufen 400 and Pantocid (Dolo 650 left out as already prescribed). Keys alone added Brufen 400 at 1-1-0-1, after food, for 7 days (version 2), and the picker reopened as "Medicine 3". Esc closed it, and Edit reopened Brufen's values. A draft with 3 stored "quote not found" checks showed none. The full suite with database tests passed: 884, with 3 skipped. Not yet committed or deployed.

D-133 committed as `899519a`, pushed, and deployed to production (`janani-private-clinic-demo-hzuh3xco0…`, aliased to the main URL).

## 6 November 2026 — open on Hospitals; sign-in ends with the browser (D-134)

**D-134 (user: "there's no authorization nothing, this is the landing page; i want to go to the hospital page first then doctors then patients").** Opening the site went straight to the last chosen doctor's patients. The sign-in cookie lasted 2 hours even after the browser closed, and the app reopened on the doctor already chosen.
- The sign-in and doctor-selection cookies no longer carry `max_age`, so they end when the browser closes. The server-side session still expires after 12 hours. Browsers set to restore the previous session ("continue where you left off") may keep such cookies.
- The shared workspace now opens on **Choose a hospital**, then the hospital's doctors, then that doctor's patients. This applies when the address has no page or just the patient list. A reload on a patient, visit or follow-up stays where it was.
- `test_private_workspace` now checks that both cookies have no lifetime. The full suite with database tests passed. The landing change was not checked in a browser locally, because the shared-admin sign-in needs the private password; the user checks it on the live site.

D-134 committed as `f6468ea`, pushed, and deployed to production (`janani-private-clinic-demo-jinxqsfkw…`).

## 6 November 2026 — Add patient beside the list (D-135)

**D-135 (user: "there's no option to add a patient").** Registering a patient was only in the top menu ("Register patient"). An **Add patient** button now sits under the Today / All patients tabs and opens the same form. It is hidden where the session cannot register. Checked locally: the button shows and opens the form. A direct load of `#/register`, which earlier showed "Cannot set properties of null", loaded correctly on both a fresh load and a reload, so that error could not be reproduced. The user's screenshot showed the tab had not been reloaded since the D-134 deploy.

D-135 committed as `eec27aa`, pushed, and deployed to production (`janani-private-clinic-demo-d9d7hlftt…`).

## 6 November 2026 — another visit; a slow first draft after each deploy (D-136)

**User:** "there's no another visit (second visit or third visit) of a patient", and "what's the use of live streaming the audio if that preparing report page still shows up and takes 10-15 seconds … if post conversation things will take 20-30 seconds before we select the medicine then there's no incentive in this app."
- **Another visit.** Once today's visit was approved, nothing offered a new one. The approved screen now has **Start another visit**, which starts a fresh recording; the visit is created when recording starts. The patient page opens today's unfinished visit first, else the latest one. Earlier visits stay listed below. The server already allowed several visits a day. Checked locally.
- **Measured on the user's live visit** (`enc-c5e44ae6f3b9`, 42 s of speech): live transcription worked (the run started with both segments transcribed), but the run still took 21 s. The models need about 6 s for this transcript (extracting 4.1 s, writing 2.1 s with `gpt-oss-120b`). Low reasoning effort was not the answer: it dropped the medicine. The rest was the hosted worker building the 250,000-name medicine index during "Checking medicines and instructions": the API warms it at start, the worker daemon never did, so the first visit after every deploy paid 14–18 s.
- **Fixed:** the hosted worker loads the index at start-up (`hosted.py` calls `main.warm_up`). The draft no longer waits for the picker's shortlist: the shortlist thread saves itself when ready, and `/shortlist` computes one if asked first. Expected: about 7 s for a short visit and about 19 s for five minutes (extracting 10 s plus writing 8 s).
- **Open (user to choose):** how to remove the remaining model time after the doctor stops.
- **Decided (user):** "Medicines first". During the visit the recommended medicines are updated from each newly transcribed piece; at stop the picker opens at once and the doctor picks medicines while the report is written, then they are added to the draft. Today's fixes were deployed first (user: "Yes, deploy now").

D-136 committed as `f4bb077`, pushed, and deployed to production (`janani-private-clinic-demo-7zzolmxar…`).

## 6 November 2026 — medicines first: pick medicines while the report is written (D-137)

**D-137 (user chose "Medicines first").** The doctor should not wait after the conversation before choosing medicines.
- **During the visit.** After each newly transcribed segment, at most once a minute per recording and one at a time, the API makes one background call (`shortlist.live_ranking`, prompt `live-shortlist-v1`): the conditions present so far, and the medicines usually prescribed for them. Each choice is resolved to a real catalogue product, as in D-122, and saved as the visit's shortlist (`method.source = live_transcript`). It is skipped once the draft exists, whose own shortlist then replaces it. On two real transcripts the call took 2.7–2.8 s and gave sensible lists. It is not made at the stop, so it never competes with the drafting calls.
- **At stop.** The report starts at once: the listen-back step and its "Create report" click are gone. The visit screen shows **Pick <patient>'s medicines** with the keyboard picker already open and focused, beside "Preparing the report" with its steps. Polls refresh only the steps, so the picker keeps its place.
- **Picks before the draft** are listed (removable). When the draft lands they are added to it in one correction; any product the draft already has is skipped, and a message says so. A picker left open carries on into the review.
- **Measured locally** (90 s of the synthetic consultation): the list was made during the visit (cough, sore throat, fever, two medicines). After stopping, the picker was open and focused within 2.5 s; Brufen was picked with the keyboard while extraction ran; the draft arrived 15 s after the stop with Brufen already added (version 2).
- **Not yet:** a pick is held in the browser only, so closing the page before the draft lands loses it. The draft's own medicine wording and the picked medicines are not reconciled beyond the product match.
- 885 passed, 3 skipped. A unit test covers the once-a-minute, one-at-a-time refresh; the live recording database test checks that the refresh is offered with the transcript so far.

D-137 committed as `382965d`, pushed, and deployed to production (`janani-private-clinic-demo-dbhf3808c…`).

## 6 November 2026 — the report waits for the medicines (D-138)

**D-138 (user, after trying D-137 live: "now it seems real time … don't want the doc to see what's happening in the background, remove that processing steps … hold the report till doc selects the meds … as soon as he has selected the med, the whole preview is available").**
- After the stop, the visit screen shows only **Pick <patient>'s medicines**: the open picker, the medicines picked so far, and **Done, show the report**. The progress steps are gone, and polls no longer redraw anything the doctor sees.
- A report that finishes while the doctor is still picking is held in the browser (`v.ready`). **Esc** in the empty picker, or the Done button, ends picking: a ready report opens at once, whole, with the picked medicines added. Otherwise a short "Putting <patient>'s report together" shows until it lands. Failures still show at once, with Try again.
- Checked locally with typed visits. The report finished while Dolo 650 was being picked and stayed hidden; Esc opened it at once at version 2 with Dolo 650 added. Pressing Done straight away showed the short wait and then the report 8.8 s later. Only `app.js` and `app.css` changed, so the Python suite was not rerun.

D-138 committed as `2b35ea3`, pushed, and deployed to production (`janani-private-clinic-demo-r01bla7nh…`).

## 6 November 2026 — keeping the WhatsApp bot up for demos

The user wants the bot running all the time for demos and asked which keys to share. **Finding:** none. Vercel production already has all five WhatsApp settings (`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_SENDER_NUMBER`) plus `WHATSAPP_TEST_NUMBERS`. A read-only `runs/connect_production_webhook.py --verify-only` passed: the Vercel webhook accepts this laptop's verify token and signature and rejects unsigned posts, and the Meta app token can read the subscription. The local send token also works (no more OAuth code 200).

**Why the bot is not always up:** Meta's callback points to a temporary `trycloudflare.com` tunnel, and no `cloudflared` is running on this laptop. A quick tunnel gets a new address each start and stops when its computer sleeps.

**Open (user's choice):** switch Meta's callback to `https://janani-private-clinic-demo.vercel.app/whatsapp/webhook` with `runs/connect_production_webhook.py` (no `--verify-only`). This changes the shared Meta app, so whoever runs the tunnel stops getting messages; agree with the team first. Vercel lacks `WHATSAPP_CLINIC_REPORT_ORG` and `WHATSAPP_CLINIC_REPORT_NUMBER`, so approvals there send no clinic copy to the test phone until those two are added.

**Switched (user: "Yes, switch it").** Ran `runs/connect_production_webhook.py`. Meta accepted the change. A follow-up `--verify-only` read confirms the callback is now `https://janani-private-clinic-demo.vercel.app/whatsapp/webhook`, active and answering Meta's check. The old `trycloudflare.com` address is saved as `previous_temporary_callback_url` in ignored `runs/whatsapp-integration/meta-setup.json`. A message from a real phone through Vercel has not been tested yet. The clinic-copy settings are still missing on Vercel.

**Tested live through Vercel (6 November 2026).** The user sent HELLO from the test phone, and the bot's reply arrived. Vercel's API and worker now run the bot with no laptop involved. Not tested through Vercel yet: delivering an approved PDF, the voice note, and lab uploads. For demos, send HELLO from the phone before approving so Meta's 24-hour window is open. A number links to one patient only, so demo visits should reuse the patient the phone is linked to.

## 6 November 2026 — pharmacy stock switched off for now (D-139)

**D-139 (user: "we don't need that pharma csv as of now for the bot to look into; keep the larger medicine base as a lookup for the recommended medicine as of now").** Pharmacy stock (D-126) now steers nothing unless `APP_PHARMACY_STOCK=1`, which is unset locally and on Vercel.
- `pharmacy.load_stock` returns an empty stock while switched off. So there is no stock bonus in medicine suggestions or search, no stock fields in search results, and no badges, same-composition swaps or approval note on drafts.
- `clinic_index` leaves out clinic products added from a stock file (`source = 'import'`), so recommendations and search come from the formulary, the Indian Medicine Dataset and the doctors' own earlier choices.
- The `pharmacy` capability is false, so the Pharmacy page and its upload are closed. The code, the tables and the imported stock rows stay, so switching it back on restores everything.
- Checked locally: a draft that had shown "Pharmacy: Out of stock" showed no stock. The shortlist came from the generic and Indian-dataset tiers, and search results carried no stock. A new database test covers the switched-off state; the stock test switches it on.

**D-140 (user: "as soon as we approve the report on the app - the patient get a message spontaneously that your visit has been completed and your report will be sent in a few minutes and rest everything as it is").**
- On approval, a text goes out first: "Hello <patient>, your visit with <doctor> at <clinic> is complete. Your doctor has approved your report, and it will be sent here in a few minutes." The PDF, voice option and everything after are unchanged.
- It is a new delivery kind, `visit_complete`, queued in the same approval transaction as the PDF, in both paths: the registered-phone path (`clinic_report_jobs`, `delivery_mode='patient'` only, not the clinic copy) and the JOIN-linked path (`patient_deliveries`). Both workers send it before the PDF. It needs no file, so it goes out on the worker's next pass after approval.
- **Assistant calls:** English only for now, because native wording needs language review (as with the voice templates). It follows the same rules as the PDF: allowed test numbers, consent, STOP and Meta's 24-hour window. With the window closed, it waits and goes out just before the PDF when the patient next writes.
- Migration `013_visit_complete_message.sql` widens the two `kind` checks. **Apply it before deploying**, or approvals will fail on the new insert. Old code works with the widened checks.
- Checks: full suite without database 852 passed, 39 skipped; new unit test for the wording. The database tests for both paths were updated (text before document, three worker passes).

**D-140 live (user: "Yes, go ahead").** Migration 013 was applied to the shared database alone (not a full `migrate` rerun), and both new checks were read back. Rollback-only database tests: 36 passed, 2 skipped. Two older tests first failed because the notice is a second queued item. The consent test read one row of two, and in the JOIN test the notice rightly goes out once the phone joins. Both tests were fixed, not the code. Deployed to production (`janani-private-clinic-demo-6afglj1i1…`, now on the main URL) from a clean copy of `2b35ea3` plus only these files. Other people's uncommitted pharmacy, sign-in and suggestion edits in this folder were left out. The webhook check still passes after the deploy. Not yet seen on a real phone. No commit was made.

D-139 committed as `b8a5c8a` on top of the visit-complete WhatsApp message (`99593a1`, D-140), pushed, and deployed to production with it (`janani-private-clinic-demo-fyfwb7iw5…`). Migration 013 for that feature was already applied.

## 7 November 2026 — Supabase egress over the free allowance (D-141)

Supabase warned that the organisation used 16.75 GB of egress against the free plan's 5.5 GB, and will restrict the projects (HTTP 402) after 9 Nov unless upgraded. Restrictions lift when the next billing cycle starts, or at once on Pro. Deleting data doesn't refund egress already used. The team will move the product to a new Supabase project before 9 Nov, so the leaks had to be fixed first or they would use up the new allowance in about two days.

**Measured** with `pg_stat_statements` (statistics since 2 Nov), read-only:

| Query | Calls | Estimated egress |
|---|---|---|
| The full Indian product list for the name index (`suggest.shared_index`), about 21 MB each time | 445 | ~9.5 GB |
| `select report from app.report_versions ...` inside `followup.restore`, from `FollowupService.scheduled()` | 505,866 | ~4.3 GB |
| `select * from app.followups where conversation->>... for update skip locked` in `scheduled()` | 235,736 | ~4.1 GB |

The worker loop waits one second when idle, and every idle tick ran `scheduled()`. That read every active follow-up and its approved report each second.

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-141 | `scheduled()` looks for due check-ins at most once a minute (`SCHEDULE_EVERY = 60`). HTTP-only instances (`APP_RUN_WORKER=0`, the hosted API) no longer preload the product name index at start; they load it on the first medicine search. The hosted worker daemon still preloads it once at start (D-136), and local runs, which draft in the same process, keep the preload. | Check-ins are due to the minute, so a minute's delay changes nothing a patient sees. API instances start far more often than the worker, and most never run a medicine search. Expected egress falls from about 3.4 GB a day to well under the 5 GB monthly allowance. Not measured yet. | User (fix before the move); Assistant (how) | Confirmed / Assistant call |

Considered and not used for this product: moving stored files to Cloudflare R2. Files are about 26 MB and not the egress source. That code went to ARDai (a separate product, now in its own folder and repo) for later use.

Checks: two new unit tests (`test_egress_fixes.py`); full suite without the database: 854 passed, 39 skipped. The rollback-only database tests weren't run, to avoid more traffic on the over-quota project. Run them against the new project after the data move. Not deployed.

## 7 November 2026 — moved to a new Supabase project (D-142, D-143)

The old project (`kymzybfrtirzpegpibcj`, organisation "AdityaRaj80's Org") reached 27.7 GB of egress against the free 5 GB, and 513 MB of database against 500 MB. The user created a new free project under a different account and put its connection string, publishable key and secret key in `../credentials`. `sync_env.py` moved the local `.env` to it. The old connection string was kept outside the repo, only for the copy.

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-142 | Run the product on the new Supabase project `izdzqrqfouorrgqhnvrv`. Production uses its transaction pooler (port 6543; the app's pool already sets `prepare_threshold=None`), as before. The old project is left untouched as a fallback. | The old project is over both free limits and will be restricted. | User | Confirmed |
| D-143 | The new project is in Tokyo (`ap-northeast-1`), so the Vercel API and worker move from `bom1` to `hnd1` (`vercel.json`). | Every page makes several database round trips. Across regions each one costs about 100 ms or more, which is the slowness D-108 fixed by moving to Mumbai. With the app beside the database, India to Tokyo is paid once per page. Data is synthetic, so storing it outside India is acceptable for the hackathon. | Assistant | Assistant call |

**Migration:**
- `create extension vector with schema extensions`.
- `tools/knowledge/upload_supabase.py` rebuilt the knowledge from the local files: 46,540 chunks and 246,068 products, with popularity loaded in the same pass. That gives 308 MB and 60 MB, against the old project's 129 MB for products after its in-place popularity update. Nothing was downloaded from the old project for this.
- `python -m voicerx.app.migrate` applied 001–013 without seed data.
- The app schema was then copied from the old project with binary COPY, in foreign-key order: 40 tables, 1,540 rows, sequences advanced.

**Checked:**
- Row counts match on every table.
- Recordings, artifacts and approved PDFs are byte-identical (sha256 and md5).
- All 66 foreign keys have no orphans.
- No queued job was copied: every WhatsApp event, delivery, run and artifact was already finished, so nothing will be sent twice.
- The new database is 410 MB of 500.

Vercel's production `SUPABASE_DB_URL` was replaced with the new transaction-pooler URL.

**Deployed (7 Nov 2026, 18:24 IST).**
- `d5bb3f1` was deployed to production from a clean `git archive` copy: `janani-private-clinic-demo-37q6mjt8j…`, now on the main URL. The container and the worker daemon both run in `hnd1`.
- Anonymous checks: the sign-in page returns 200, `/api/v1/session` and `/api/v1/patients` return 401, an unsigned webhook gets 403.
- `runs/connect_production_webhook.py --verify-only` passed. The Meta callback is unchanged and healthy.
- Worker log: "Private worker startup verified: database and PDF renderer ready", then "Medicine index loaded."
- The new project's `pg_stat_statements` shows production working against it at the new rates. Over two minutes: 2 follow-up schedule checks (once a minute; before the fix, every second) and 8 report reads. The estimate is about 75 MB of egress a day, about 2 GB a month, with today's 4 active follow-ups. It grows with each active follow-up.
- `vercel daemons instances list` shows one worker instance (`hnd1`).
- Not verified by the assistant: signing in with the shared password (the user's step), a recording-to-approval run, and a WhatsApp message through the bot on the new database.

**Open.** Something outside this laptop and outside the current deployment still runs the old code's worker loop against the old project: about 60 queries a minute through its pooler. Most likely a teammate's local copy with the old `.env`. It can't affect the new project. Teammates should update their `.env` from `../credentials`, and the old project can be paused in the Supabase dashboard once the new one is confirmed. The old connection string is kept outside the repo in `../credentials/old-supabase/` for a rollback.

**Local check against the new project (9 Nov 2026).** The app ran on this laptop on port 8002 with `APP_DEV_LOGIN=1` and `APP_RUN_WORKER=0`, so no worker claimed jobs and nothing was sent on WhatsApp.
- The development sign-in listed the copied doctors.
- Signed in as Aditya Raj, the hospital's three patients appeared with their follow-up tasks (3) and review counts.
- With the local artifact copies (`runs/app`) moved aside, so files had to come from the database as on Vercel, Virat's two approved report PDFs (78,712 and 81,783 bytes) and FHIR bundles downloaded intact (200). A stored recording returned all 1,177,264 bytes as `audio/webm`.
- Medicine search ("dolo 650") returned DOLO 650 first. The first search took 15 s, because this process loaded the product index on first use (D-141) from India to the Tokyo database. The next search took 1.2 s. On Vercel, beside the database, the first-search load is shorter but still costs a few seconds once per new API instance.
- No server errors. The only browser error was the expected 401 from the session check before sign-in.

Still for the user: sign in on the live site once, and send HELLO from the test phone.

## 9 November 2026 — WhatsApp checked, medicine search sped up, long medicine names wrap (D-144, D-145)

**WhatsApp.** The approval at 21:01 queued the visit-complete text, the PDF and the voice button as `waiting_for_window`. The new database had no inbound WhatsApp event since 6 Nov, and production logs showed no webhook call in the last hour. A read-only Meta check found everything in order: the callback is production with `messages` subscribed, the send token is valid and permanent, and the test number (ends 3389) is connected with quality GREEN. So the bot was correctly waiting for the patient's 24-hour window (D-140). After the user sent HELLO from the registered phone, the report and the other messages arrived. No code change.

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-144 | The Indian product list for the name index ships with the deploy as `data/snapshots/indian_products.json.gz`, built from the local dataset by `tools/knowledge/build_products_snapshot.py` with the same row rules as `upload_supabase.py`. The app uses it when its count matches the table; a stale, missing or unreadable file falls back to Postgres. Every process now preloads the index at start (index first, then the embedding model), so the first medicine search is fast. The file is git-ignored and added to the deploy copy, because the dataset's licence doesn't clearly allow republishing it in this public repo. `data/snapshots/README.md` keeps the folder for the Dockerfile's `COPY`. | After D-141 the API loaded the list from Postgres on the first search: about 15 s from India and several seconds beside the database, which the user hit. From the file it loads in about a second, with no Supabase egress. | User (fix the speed); Assistant (how) | Confirmed / Assistant call |
| D-145 | The last-visit summary's value column is `minmax(0, 1fr)`, and panels allow long words to wrap (`overflow-wrap: anywhere`). The CSS and JS cache version moves to `20261109a`. | A medicine label such as "(PARACETAMOL/ACETAMINOPHEN+TRAMADOL)" has no natural break, so the `1fr` column grew past the card into the WhatsApp panel. | User (bug); Assistant (fix) | Confirmed / Assistant call |

**Checks:**
- The snapshot matches the table: 246,068 products, the same id, name, composition, manufacturer and popularity.
- Four unit tests cover preload order, snapshot use, and falling back for a stale, missing or broken file.
- Locally, against the new project, the first search right after a fresh start took 1.1 s instead of 15 s. "dolo 650", "ultracet" and "pan 40" each found the expected product first. Most of the 1.1 s is the India-to-Tokyo database round trip.
- On Akshay's page no text extends past the summary card; the ULTRACET label wraps onto three lines.
- Observed, not changed: "augmentin 625" ranks "Megamentin 625 Tablet" first. Ranking is the same as before this change.

**Deployed (9 Nov 2026, 21:15 IST).**
- `5161e38` was deployed to production from a clean `git archive` copy plus `data/snapshots/indian_products.json.gz`: `janani-private-clinic-demo-k2ml3zf6v…`. The sign-in page returns 200 and `/api/v1/session` 401.
- The API instances restarted under the new build at 15:45 UTC. They restart often (shutdowns at 15:37), which is why loading from the file matters.
- Proof that production uses the snapshot: before restarting the worker instance, `pg_stat_statements` counted 8 full product-list reads and 7 row-count checks. After the restart the counts were 8 and 8. The new process checked the count and took the list from the file, with no full read.
- The worker came back ready.
- Not checked live by the assistant: a signed-in medicine search, and the summary card on the live site. Both need the shared password.

## 9 November 2026 — a read-only guest preview for recruiters (D-146)

The user asked for a guest login to put on a CV. Recruiters click it and land on a doctor's dashboard as "Guest". They see every part of the product: consultations, medicines, reports, WhatsApp follow-ups. Nothing they do may use the paid APIs. Notes on each screen explain what is what.

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-146 | **Who the guest is.** A made-up clinic, `clinic-guest` ("ARDAI Guest Clinic"), with one made-up doctor, `doctor-guest` ("Dr Guest"). Visitors enter with **Explore as a guest doctor** on the sign-in page (`POST /api/v1/auth/guest`) or through the one-click link `/guest`. A guest session lasts 2 hours.<br>**Read-only.** `session_of` refuses every unsafe method (POST, PUT, PATCH, DELETE) for a guest session with 403 and a plain message. Only sign-out and the drug-label look-up are allowed; the look-up is a local embedding search with no model call. A visit's medicine shortlist is never generated for a guest. The page also stops these clicks before any request, shows the same message, and does no background polling for guests.<br>**What a guest sees.** A banner, plus a "Guest note" on the patient list, patient page, recording card, draft review, approved visit, follow-ups, WhatsApp conversation and registration. The notes can be hidden. Guests open on All patients, and each patient opens on their latest visit.<br>**Where the data comes from.** `tools/demo/seed_guest.py` copies the finished synthetic visits of the demo hospitals into the guest clinic: 5 patients, 18 visits, 68 report versions, 13 approvals and 13 follow-ups. Each copy gets a new, stable id. Every clinic and doctor name is replaced, report fingerprints are recomputed, and the 13 approved PDFs and FHIR bundles are printed again under the guest names. Phones, WhatsApp contacts, join codes, provider message ids, recordings and unfinished deliveries are not copied. Rerunning the script replaces the guest copy and leaves the source records untouched. | The user wants recruiters to see the whole UI without using the APIs. A separate clinic keeps visitors out of the team's records, and the server-side refusal holds even when the page is bypassed. With no contact or pending job on any guest record, the worker has nothing to send or draft for them, and an inbound WhatsApp message can't match a guest patient. | User (guest login, read-only, notes); Assistant (how) | Confirmed / Assistant call |

**Checks (local, against the shared database; worker off).**
- Unit tests: 675 passed, 1 skipped. Four new tests cover the guest rules: reads allowed, every write refused, sign-out and look-up allowed, other doctors unaffected, and the guest flag sent to the page.
- In the browser: **Explore as a guest doctor** opened Dr Guest's dashboard with the banner and notes. Akshay's approved visit showed "Approved by Dr Guest". Virat's draft showed its checks. Answering a check showed the read-only message, and the server answered a direct approval with 403.
- Also in the browser: medicine search ("dolo 650") and the drug-label look-up worked. The follow-up page showed the WhatsApp conversation as "Dr Guest at ARDAI Guest Clinic". `/guest` from a signed-out browser landed on the patient list as Dr Guest. At phone width the page had no sideways scroll.
- A guest PDF reads "ARDAI Guest Clinic" and "Dr Guest". No other clinic or doctor name appears in any guest report, PDF or conversation.

**Deployed (9 Nov 2026, about 23:40 IST).** The user said "Yes, deploy it". It went out from a clean `git archive` copy of `5b59d9c`, plus these changes and the product snapshot, as `janani-private-clinic-demo-ksqqbr3xl…`, aliased to the main URL. Checked on the live site:
- `/guest` opened the dashboard as Dr Guest at ARDAI Guest Clinic, with the banner and notes.
- The first medicine search ("dolo 650") answered in 388 ms with DOLO 650 first.
- Approving a draft and starting a run both returned 403. A malformed registration was rejected with 422 before reaching the guest check, so nothing was written.
- An approved PDF downloaded (84,884 bytes).
- The public sign-in page shows **Explore as a guest doctor**.
- The link for a CV is `https://janani-private-clinic-demo.vercel.app/guest`.

## 9 November 2026 — the hackathon product is called VoiceRX (D-147)

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-147 | Every user-facing "ARDAI" in this repo becomes "VoiceRX". That covers the page titles, the logo text, the sign-in page, the dashboard and guest notes, the PDF title, the WhatsApp bot's help text, the API titles and the older v1/v2 pages. The guest clinic is now "VoiceRX Guest Clinic"; `seed_guest.py` was rerun, so its records, chats and 13 PDFs carry the new name. The cache version moves to `20261109c`. Code names (`voicerx` package, ids) are unchanged. | The user: "for the hackathon it's VoiceRX". ARDAI is the name of the product being built on top of this one (the separate ARDai repo). | User | Confirmed |

**Checks.** No "ARDAI" is left in the app's code, templates or pages, and none in the guest clinic's reports, chats or PDFs (a reprinted PDF reads "VoiceRX Guest Clinic" and "Dr Guest"). Unit tests: 675 passed, 1 skipped. Earlier entries in this runbook keep the name they were written with.

**D-147 deployed (9 Nov 2026).** The user said "Yes, deploy it". Deployed from a clean `git archive` copy of `db82ab7` plus the rename and the product snapshot, as `janani-private-clinic-demo-mkte0ro9o…`, aliased to the main URL. On the live site, `/guest` opens "VoiceRX for Doctors" with the VoiceRX logo, Dr Guest and "VoiceRX Guest Clinic". The sign-in page title is "Sign in to VoiceRX". "ARDAI" appears on neither page.

## 10 November 2026 — a second address: gnani-private-clinic-demo.vercel.app (D-148)

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-148 | `gnani-private-clinic-demo.vercel.app` is added as a second production domain of the same Vercel project (`vercel domains add … janani-private-clinic-demo`). The old address stays, so the hackathon submission, shared links and the Meta WhatsApp webhook (registered on the old address) keep working. Production `APP_ALLOWED_ORIGINS` becomes both addresses. Before the change, a probe with a guest session showed only `https://janani-private-clinic-demo.vercel.app` allowed among the candidates tried. The full settings file was not pulled, so no other secrets were read. No code change. | The user wants the CV link to read gnani-…: "can the name be changes to Gnani-private-clinic-demo.vercel.app ?". Without the new origin, the server refuses every change on the new address ("request from an origin that is not allowed"); a probe showed exactly that. | User (new address); Assistant (keep both, how) | Confirmed |

**Before the redeploy.** The new address already served the VoiceRX sign-in page (200) and `/guest`, but the guest's drug-label look-up returned 403 there until a redeploy picks up the new setting.

**Redeployed (10 Nov 2026).** The user said "Yes, redeploy". Deployed from a clean `git archive` copy of `701fac5` plus the product snapshot, as `janani-private-clinic-demo-9t4jrusut…`. Its aliases are both `gnani-private-clinic-demo.vercel.app` and `janani-private-clinic-demo.vercel.app`. With a guest session on each address:
- The drug-label look-up returned 200 on both.
- An approval returned 403 on both: the guest is still read-only.
- `/guest` redirected to the patient list on both.

The webhook on the old address answers an unsigned request with 403, as before. The CV link is now `https://gnani-private-clinic-demo.vercel.app/guest`.

## 10 November 2026 — Vercel's free CPU nearly used up; worker off, lazy loading (D-149)

Vercel emailed at 16:24: the free team `aditya2704raj-8181` had used 90% of its **Fluid Active CPU (4 hours a month)**. At 100% the project is paused, which would take down the hackathon link and the guest preview. Nobody was using the site. The free plan's CLI shows no breakdown (`vercel billing usage` has no data for a Hobby team), so the two causes below are reasoned from the setup, not measured.
- The always-on worker daemon polls the database about once a second, around the clock.
- Since D-144, every hosted API instance loads the product index and the embedding model at start, and Vercel starts instances often.

The user said: "decide for me what can we do considering all the situations".

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-149 | **The worker daemon is removed from `vercel.json`**, so nothing runs while the site is idle. Without it, recordings are not drafted, PDFs for new approvals are not printed, and WhatsApp neither sends nor replies. Browsing, the guest preview, existing PDFs, medicine search and the look-up all work.<br>**Hosted API instances (`APP_RUN_WORKER=0`) no longer preload anything at start.** The product index loads from the shipped snapshot on the first medicine search (about a second), and the embedding model on the first look-up. Local runs and worker processes still preload.<br>**To switch the worker back on** (for example, for a live judging session), add this to `vercel.json` and redeploy: `"daemons": {"worker": {"root": ".", "entrypoint": "Dockerfile.vercel", "command": ["python", "-m", "voicerx.app.hosted", "worker"], "instances": {"hnd1": 1}, "resources": {"requests": {"memory": "2Gi"}}, "terminationGracePeriodSeconds": 300}}`. | The hackathon is submitted, and what judges and recruiters open is the browsing and guest side, which needs no worker. Keeping the project from being paused matters more than live drafting. The CPU allowance resets with the monthly cycle; the worker can return for a demo when there is headroom. | User (asked the assistant to decide); Assistant | Assistant call |

Unit tests: 675 passed, 1 skipped.

**D-149 deployed (10 Nov 2026).** The user said "Yes, deploy it". The deploy (`janani-private-clinic-demo-88vttqg27…`) answers on both addresses, and `vercel daemons list` is empty. A guest saw all 5 patients on both. The first medicine search on a fresh instance took **10.6 s**, not the "about a second" estimated above: loading the snapshot and building the index in the container is slower than on a laptop. Later searches took 0.6–0.9 s. That one slow search per new instance is the price of not preloading.

## 10 November 2026 — worker back on to record the demo (D-150)

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-150 | The worker daemon is back in `vercel.json` (same settings as before D-149), so recording, drafting, PDFs and WhatsApp work again. It is to be switched off again (D-149) once the demo video is recorded, because the free 4 hours of active CPU a month were already 90% used. | The user: "up the server, whatsapp, recording everything — we have to record a demo of the entire workflow". | User | Confirmed |

**Deployed (10 Nov 2026, 23:07 IST)** as `janani-private-clinic-demo-otq5sb0wz…`. The build took 17 minutes because it builds the worker image too. The worker instance is alive in `hnd1`, and its log shows "Private worker startup verified: database and PDF renderer ready", then "Medicine index loaded." The site returns 200, and an unsigned webhook request gets 403 as before.

## 10 November 2026 — submitted; worker off for good (D-151)

| ID | Decision | Why | Decided by | Status |
|---|---|---|---|---|
| D-151 | The demo is recorded and the hackathon submitted. The worker daemon is removed again (as in D-149), leaving only the HTTP app. The guest preview, browsing, past reports and PDFs, medicine search and the look-up stay live. Recording, drafting, new PDFs and WhatsApp are off. To turn the worker back on, follow the note in D-149. | The user: "submitted, remove the worker and everything so that the compute time is saved; we just want the demo version to be alive". | User | Confirmed |

**Deployed (10 Nov 2026)** from a clean copy of `57ab2ab` plus the product snapshot, as `janani-private-clinic-demo-j15wgun6p…`. `vercel daemons list` is empty. `/guest` signs in as Dr Guest @ VoiceRX Guest Clinic.
