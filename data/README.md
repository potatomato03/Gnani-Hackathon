# Data

Everything here is synthetic. We don't train any model, so we need small, carefully checked sets, not large ones. No public dataset has Hinglish doctor dictation with a gold structured note and Indian brand names, so we build our own and use public sources only as ingredients.

The biggest effort is checking medicine facts and expected answers, not generating audio.

## Rules

The challenge bans real phone numbers, account numbers, Aadhaar, PAN and recorded calls from the project and demo, and tells entrants to use synthetic data. It says nothing about public datasets, so each one still needs its licence checked, its authors credited, and a clear reason to be here.

- No real patient, record, recording or ID, in any form.
- Nothing copied from a real hospital document, not even as a template.
- Phone numbers use `+91-00000-NNNNN`. Indian mobile numbers don't start with 0, so these can't belong to anyone.
- Every record carries `synthetic: true`, and the app labels synthetic data on screen.
- Audio and provider caches stay out of git.
- Prisma accuracy results stay private until Gnani gives written consent. See [DECISIONS.md](../docs/DECISIONS.md).

## Five kinds of data

Keep these apart. A note the app generates is an output, never a correct answer to score against.

| Group | Meaning | Example | Folder |
|---|---|---|---|
| Reference data | Facts the app looks up while working | Brand to composition | `formulary/`, `rules/`, `drug_cards/` |
| Patient and clinic data | What belongs to one encounter | A patient's recorded allergies | `seed/` |
| Evaluation data | Inputs paired with checked expected results | Audio and the correct prescription | `eval/` |
| Configuration and templates | How the app interprets and presents things | Report layout, approved answer wording | `services/api/voicerx/` |
| Generated records and logs | What the app produces as it runs | Transcripts, approved notes, flags | Database, never `eval/gold/` |

Evaluation answers must never reach prompts, examples or anything the app can retrieve at runtime.

## What we build

These are build targets. They don't prove clinical reliability.

### Voice ingestion

| Set | Amount | Folder |
|---|---|---|
| Case specs | 12 first, up to 60 case families | `eval/cases/` |
| Dictation scripts | Hinglish, Hindi, English, some Telugu and Tamil | `eval/scripts/` |
| Clean audio | 60 | `eval/audio/` (ignored) |
| Noisy variants | 20, each paired with its clean version | `eval/audio/` (ignored) |
| Actual-spoken transcripts | One per clean audio file | `eval/transcripts/` |
| Two-speaker consult clips | A few | `eval/audio/` (ignored) |
| Keyterms and glossary | At most 200 sent per request | `formulary/` |

### Report generation

| Set | Amount | Folder |
|---|---|---|
| Clinic, doctors, patients | 1 clinic, 3 doctors, 30 patients | `seed/` |
| Formulary | ~100 hand-checked products | `formulary/` |
| Dosing phrases | 50 to 100 phrase families, with what each one does and doesn't state | `rules/` |
| Dose, allergy and duplicate rules | Demo drugs only | `rules/` |
| Gold notes and prescriptions | One per case family | `eval/gold/` |
| Seeded rule failures | 20, plus 20 matched negatives | `eval/rule_cases/` |

A formulary row must separate strengths, immediate and modified release, tablet and syrup, and single and combination products. Product strength is not the dose given.

### Patient agent

| Set | Amount | Folder |
|---|---|---|
| Drug cards | Every drug the agent explains | `drug_cards/` |
| Answer templates | Per intent and language | `services/api/voicerx/agent/templates/` |
| Urgent script and red-flag phrases | Hindi, English, Telugu | `rules/` |
| Patient questions | 40 normal, 40 adversarial, 15 urgent, 15 matched negatives | `eval/agent/` |
| Full voice sessions | At least 10 | `eval/agent/` |

The expected result for a question is an action plus allowed and forbidden claims, not one exact sentence. If the visit says "after food" and nothing about milk, then "can I take it with milk?" must escalate, and "yes, milk is fine" is a forbidden claim.

Drug cards state what they apply to: product, form, route, population and jurisdiction. openFDA holds US labels, so it is never the only source for an Indian product.

### Dashboard

| Set | Amount | Folder |
|---|---|---|
| Linked visit histories | At least 5 patients with 3 visits each | `eval/history/` |
| Medication changes | Started, continued, changed, stopped, restarted, unreconciled | `eval/history/` |
| Ask-the-record questions | ~20, including ones with no answer | `eval/history/` |

Derive histories from reviewed cases, so the records agree. A good test: visit 1 prescribes a medicine, visit 2 stops it, and at visit 3 the patient asks whether to continue.

### Shared

| Set | Use | Folder |
|---|---|---|
| Permission fixtures | Other doctors, expired links, wrong-patient requests | `services/api/tests/` |
| Failure fixtures | Lost final segments, duplicate requests, interrupted calls | `services/api/tests/` |
| Provider responses | Real STT, TTS and LLM payloads, cached | `eval/fixtures/` (ignored) |
| FHIR examples | Official ABDM examples and deliberately broken bundles | `services/api/tests/` |

## How we build a case

1. **Write the case spec.** Record the facts, assertions and medicines as structured data. Mark what gets spoken, what is already in the chart, and what stays unavailable to the app.
2. **Assign the family to a split.** Do this before making any variants.
3. **Generate the script.** The LLM writes natural language only: pauses, code-mixing, corrections. It gets the facts that must appear and the facts that must stay unstated, and it may not add clinical claims.
4. **Check the script.** Code compares it with the spec, then a person reads it. A native speaker checks Telugu and Tamil.
5. **Render clean audio once.** Use Timbre and cache the result. Test credit use on 5 clips first, because the cost of a credit isn't published.
6. **Listen.** Write what was actually spoken, and mark mispronounced, dropped or unclear words.
7. **Make noisy variants from the clean audio.** Use MUSAN noise files and room impulse responses. Cross-talk is a second Timbre voice, never real speech.
8. **Attach evidence.** Quotes come from the actual-spoken transcript, not the script. If the audio dropped "not", the gold follows the audio. Reconcile any difference with the spec.
9. **Review independently.** The teammate who didn't write the case checks it.

If noise makes a dose unintelligible, the expected behaviour is to ask or flag it, not to recover the hidden script.

The expected output follows what the app can see. If the story says no allergies but nobody said so and the chart doesn't either, the expected output is "unknown".

## Expected output by stage

Each stage has its own expected output, so a failure can be traced to where it started.

| Stage | Input | Expected output |
|---|---|---|
| Speech recognition | Audio | Actual-spoken transcript |
| Speaker attribution | Consult audio | Speaker turns, with roles only when established |
| Extraction | Transcript and chart context | Facts supported by those inputs |
| Medicine matching | Spoken name and formulary | The product, a candidate set, or unresolved |
| Report | Reviewed record | Correct fields, omissions, uncertainty and evidence |
| Patient agent | Approved visit, question | Action, allowed claims, forbidden claims |
| Dashboard | Ordered visits | Chronology, current status, source references |
| Full pipeline | Audio and context | Final record and required review actions |

## Splitting

- **Unit:** the case family, never a file. One family holds all its languages, voices, clean and noisy audio, corrections, paired variants, patient questions and visits.
- **Same family:** everything for one fictional patient, cases that differ only by name or age, and anything derived from one source case.
- **Size:** start with 12 families. Grow to at most 60: 20 development and 40 held-out. Unreviewed cases don't count as gold, so if time runs short, shrink held-out to 20 rather than weakening review, and report the real count.
- **Model choice:** pick prompts and models on the development set. The held-out set is for the frozen system only.
- **Voices:** keep 3 or 4 of the 13 Timbre voices for held-out audio only.
- **Keyterms:** build the keyterm list and glossary from the formulary and development cases only, and freeze them before writing held-out scripts.
- **Out-of-formulary brands:** held-out scripts include some, so the matcher has to say "unresolved".
- **Formulary:** shared across splits, because the app is meant to consult it.

Tag every family and check the counts after splitting: language, capture mode, negation and uncertainty, medicine name difficulty, schedule type, corrections, noise and agent behaviour. 40 families can't cover every combination, so we report the gaps.

Keep two tracks in reporting: everyday cases and challenge cases. One average would hide where the system struggles.

## Matched pairs

Each pair differs in one meaningful way and stays in one family.

| Pair | Tests |
|---|---|
| "No fever" / "Fever" | Negation |
| "My father has diabetes" / "I have diabetes" | Who it applies to |
| "Left hand" / "Right hand, sorry, left hand" | Corrections |
| "Used to take" / "Start taking" | Past versus new medicine |
| "Once daily" / "One tablet once daily" | Invented quantity |
| "Allergy not discussed" / "No known allergies" | Unknown versus none |
| "Investigate for" / "Confirmed" | Suspicion versus diagnosis |

Every rule test also needs a close case that must not trigger, or a system that warns about everything looks successful.

## Review

| Layer | Checks | Done by |
|---|---|---|
| Structure | Required fields, IDs, units, evidence references, dates | Code |
| Consistency | Conflicting facts, additions, missing facts | Code, LLM as a flag only |
| Language | Natural wording, translation, what was actually spoken | Teammate, native speaker |
| Annotation | Expected output follows from the evidence | The other teammate |
| Clinical | Rules, drug cards, urgent wording, a sample of starter cases | Doctor |

Gold records what was said, not whether the treatment was right, so a teammate can check most of it. Two LLMs agreeing doesn't make something correct.

Status moves through `generated`, `auto_checked`, `human_reviewed`, `adjudicated`, `released`. Clinical and language review are separate flags. Only `released` cases are scored, and anything without clinical review stays labelled that way.

## Manifest

Every released item records:

```
case_id, family_id, patient_id, source_parent_id
split, track, language, scenario_tags
source_and_license, generation_version
reference_version, annotation_version
review_status, clinical_review, language_review
voice, noise_source, mix_level, audio_format
audio_hash, transcript_hash, expected_output_hash
```

## Before the final run

- No family or patient crosses splits, and no duplicates or disguised duplicates do either.
- Every evidence quote exists in the transcript and supports its fact.
- Every scored item is `released`.
- Test answers are absent from prompts, examples and retrieval.
- Model, prompts, rules, catalogue and code are frozen.

A held-out case we inspect and tune against becomes regression data and no longer counts as held-out.

## Reporting

Count families, not files: 300 audio variants from 40 families are not 300 independent cases. Report by language and noise, with family counts, and measure critical facts, unsupported additions, omissions and correct abstention separately.

Timbre audio tends to be cleaner and more consistent than real doctors, so these results don't show real-clinic performance.

## Sources

### Used

| Source | Licence | Use |
|---|---|---|
| [Indian Medicine Dataset](https://github.com/junioralive/Indian-Medicine-Dataset) | MIT on the repo, data origin not stated | Lookup for brand, composition and strength. Every row we keep is hand-checked. |
| [IndianDrugMCQA](https://huggingface.co/datasets/ekacare/indian_drug_mcqa) | MIT | Cross-check of brand to generic. It has typos and no strengths. |
| Manufacturer product pages | Varies | Confirm a brand's identity, recorded per row |
| [MUSAN](https://www.openslr.org/17/) | CC BY 4.0 | Noise files only, not the speech or music folders |
| [RIRS_NOISES](https://www.openslr.org/28/) | Apache 2.0 | Room reverb |
| [Faker](https://github.com/joke2k/faker) | MIT | Fictional names with the `en_IN` locale. Its phone numbers are not used. |
| [ABDM FHIR guide](https://www.nrces.in/ndhm/fhir/r4/StructureDefinition-DocumentBundle.html) | Not confirmed | Official examples for validating our bundles |

### Reference or optional

| Source | Licence | Use |
|---|---|---|
| [Synthetic Medical Dictation](https://huggingface.co/datasets/modulate/synthetic-medical-dictation) | CC BY 4.0 | Method reference only: English, US and UK voices |
| [openFDA drug labels](https://open.fda.gov/apis/drug/label/) | See openFDA terms | Only where ingredient, form and route apply |
| [ACI-Bench](https://github.com/wyim/aci-bench) | CC BY 4.0 | Optional, after the core: outside English check of extraction. No Indian brands. |
| [PriMock57](https://github.com/babylonhealth/primock57) | CC BY 4.0 | Optional real-voice check. Ask Gnani first, and keep it out of the repo and demo. |

### Not used

| Source | Why |
|---|---|
| DISPLACE-M | Real doctor-patient recordings, released for its own challenge only |
| IndicVoices | Real people's speech, not needed for a synthetic corpus |
| Eka Medical ASR Evaluation | Real voices. Not in this repo or the demo. |
| Hinglish-CoT-Medical | No licence stated |
| Synthea | No India configuration, and histories must come from our reviewed cases |
