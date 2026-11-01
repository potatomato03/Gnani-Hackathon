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
| Audio | None | Team to decide on the free route in [Free audio research](#free-audio-research) |
| Gold notes | None, by design. They need real audio first. | Follows audio |
| Application code | None | Start `contracts/` and extraction |
| LLM | Not chosen, free tier first | Run the typed test on free models |
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
| D-36 | Use the free audio route below before spending Gnani credits. | See [Free audio research](#free-audio-research). | Proposed |

### Replaced

| ID | Original | Replaced by |
|---|---|---|
| D-37 | Prepay about $50 for Claude on day one. | D-01. On free models first, this isn't needed yet. |
| D-38 | Keep the repo private. | D-04. The repo is public, so sensitive material stays out of it instead. |
| D-39 | Store downloads in `data/external/`. | D-16. Moved to `DATA` in the root folder. |

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
| Wrote this runbook | This commit. |

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
- [Synthetic Medical Dictation](https://huggingface.co/datasets/modulate/synthetic-medical-dictation)
