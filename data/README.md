# Data

Everything here is synthetic. No public dataset has Hinglish doctor dictation with a gold structured note and Indian brand names, so we build our own and use public sources only as ingredients.

## Rules

The challenge bans real phone numbers, account numbers, Aadhaar, PAN and recorded calls from the project and demo, and tells entrants to use synthetic data.

- No real patient, record, recording or ID, in any form.
- Nothing copied from a real hospital document, not even as a template.
- Phone numbers use `+91-00000-NNNNN`. Indian mobile numbers don't start with 0, so these can't belong to anyone.
- Every record carries `synthetic: true`, and the app labels synthetic data on screen.
- Audio and provider caches stay out of git. Rendered corpus audio lives in `data/eval/audio/`, which is ignored.

## What we build

| Set | Size | Folder |
|---|---|---|
| Clinic, doctors, patients | 1 clinic, 3 doctors, 30 patients | `seed/` |
| Formulary | ~100 hand-checked products | `formulary/` |
| Dose and class rules | Demo compositions | `rules/` |
| Drug cards | Demo drugs, doctor-reviewed | `drug_cards/` |
| Consult scripts | 60, split 20 dev and 40 held-out by scenario family | `eval/scripts/` |
| Gold notes and spans | One per script | `eval/gold/` |
| Noisy variants | 20, paired with clean versions | `eval/audio/` (ignored) |
| Agent questions | 40 in-scope, 40 adversarial, 15 urgent plus negatives, 10 full voice calls | `eval/agent/` |
| Seeded rule failures | 20 with matched negatives | `eval/rule_cases/` |

## How we build the corpus

1. Write the gold first: each scenario starts as structured JSON (facts, medicines, corrections, negations).
2. Generate the dictation from the gold with an LLM, in Hinglish, Hindi, English, Telugu or Tamil.
3. Check by code that every gold value appears in the script as an exact quote.
4. A team member reads every script, and a native speaker checks Telugu and Tamil.
5. Render once with Timbre, cache the audio, listen to every clip and record what was actually spoken.
6. Add noise with MUSAN noise files and room impulse responses. Cross-talk is a second Timbre voice, never real speech.

## Sources

| Source | Licence | Use |
|---|---|---|
| [Indian Medicine Dataset](https://github.com/junioralive/Indian-Medicine-Dataset) | MIT on the repo, data origin not stated | Lookup for brand, composition and strength. Every row we keep is hand-checked. |
| [IndianDrugMCQA](https://huggingface.co/datasets/ekacare/indian_drug_mcqa) | MIT | Cross-check of brand to generic. It has typos and no strengths. |
| [MUSAN](https://www.openslr.org/17/) | CC BY 4.0 | Noise files only, not the speech or music folders |
| [RIRS_NOISES](https://www.openslr.org/28/) | Apache 2.0 | Room reverb |
| [Faker](https://github.com/joke2k/faker) | MIT | Fictional names with the `en_IN` locale. Its phone numbers are not used. |
| [Synthetic Medical Dictation](https://huggingface.co/datasets/modulate/synthetic-medical-dictation) | CC BY 4.0 | Method reference only: English, US and UK voices |

## Not used

| Source | Why |
|---|---|
| DISPLACE-M | Real doctor-patient recordings, released for its own challenge only |
| IndicVoices | Real people's speech, not needed for a synthetic corpus |
| Eka Medical ASR Evaluation | Real voices. Not in this repo or the demo. |
| Hinglish-CoT-Medical | No licence stated |
