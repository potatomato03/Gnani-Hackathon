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
| Gnani API key | Not configured | Create it on the primary registrant's account |
| Repo | Work is on `aditya/data-setup`. `main` holds only the first commit. | Team merges when ready |
| Downloaded data | Done, 7 datasets in `../DATA`, about 5 GB. Only on one machine. | Share the folder with the teammate |
| Case families | 12 built, all `auto_checked` | Teammate review |
| Clinical review | Not started, no doctor booked | Book a doctor, ideally before 8 Nov |
| Language review | Not started | Find Telugu and Tamil readers |
| Formulary | 25 of about 100 rows, all `verified: false` | Hand-check each row, then extend |
| Audio | 22 of 25 clips rendered, all transcribed by Whisper. 3 wait on Gemini's daily limit. | Render the last 3, then listen to all of them |
| Extraction and report | Spec and plan final: 19 tasks, Gemini first with a local fallback (D-70). Aditya approved building it. Not built. | ASTRA builds it Native, following the plan's "Handoff to ASTRA". Claude then reviews the branch (D-71). |
| Mistral | Dropped. The key is rejected as invalid, and the plan couldn't be activated. | None |
| Local model | `qwen3:8b` and `qwen2.5:7b` in Ollama, stored in `models/ollama` in the root folder. First probe passed. | Compared with Gemini in Task 16 |
| Gemini text models | Overloaded on 2 Nov (HTTP 503) | Retry later. The planned client retries and falls back automatically. |
| Gemini key | Accepted by Google, stored in the ignored `.env` | None |
| Local transcription | Working on the GPU. `.venv` and `models` are in the root folder, on one machine only. | Teammate repeats the setup under [How to run](#how-to-run) |
| Gold notes | None, by design. They need real audio first. | Follows audio |
| Application code | None | Start `contracts/` and extraction |
| LLM | `gemini-3.8-flash` first, `qwen3:8b` on the local GPU as fallback | Task 16 compares them on the typed scripts |
| Evals | None | Needs the pipeline |

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
`n- Task 4 live verification: Gemini gemini-3.8-flash and Ollama qwen3:8b each returned a valid tiny-schema object on one attempt. No adapter changes were needed.

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
