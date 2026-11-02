# Extraction and Report Implementation Plan

> **For agentic workers:** this plan runs Native. One agent, ASTRA, implements every task in order in one working session, using superpowers:executing-plans if available. Claude reviews the whole branch afterwards. Read "Handoff to ASTRA" below before Task 0. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a consultation transcript into a checked draft report, then an approved PDF report and ABDM FHIR bundle, through two model stages with code checks between them.

**Architecture:** Stage 1 (model) extracts quoted items into `extraction.json`. Check 1 (code) verifies quotes, ties each phrase to its own medicine, matches medicines, and parses doses into fixed values. Stage 2 (model) writes report lines that cite stage 1 items. Check 2 (code) verifies each line against its citations. Code assembles the draft, with the medicine table, the current medicines and a frozen copy of the records it used. The doctor clears flags through audited corrections, each making a new draft version, then approves it. Code renders the PDF and FHIR bundle from the approved record.

**Tech Stack:** Python 3.12, Pydantic 2, Gemini API (`gemini-3.8-flash`) with a local Ollama model (`qwen3:8b`) as fallback, rapidfuzz, Jinja2, headless Edge or Chromium, pypdf (tests only), pytest.

**Spec:** `docs/superpowers/specs/2026-11-02-extraction-and-report-design.md`

## Global Constraints

- **Environment:** run everything from the repo root with the root folder's environment, `../.venv/Scripts/python`. Module commands (`-m voicerx…`) need `PYTHONPATH=services/api`. Tests find the package through `conftest.py`.
- **Model and keys:**
  - Use `gemini-3.8-flash` for both stages, falling back to the local Ollama model `qwen3:8b`. Mistral is dropped (runbook D-70).
  - Settings come from `.env`: `GEMINI_API_KEY` and `GEMINI_API_KEY_2`, then `OLLAMA_MODEL` (`qwen3:8b`) and `OLLAMA_HOST` (`http://localhost:11434`).
  - Send a key only in its provider's auth header. Never print it, log it, or write it to a run file or cache file. Ollama takes no key.
  - The two Gemini keys may belong to one Google project and share its quota. Treat the second as a fallback, not as extra allowance.
  - Ollama keeps its models in `D:\Study\JANANI\models\ollama`, set by the user variable `OLLAMA_MODELS`. The laptop's GPU has 8 GB, so models above about 8B parameters don't fit.
- **What the model never supplies:** composition, strength, time slots, dates, the medicine table, or current medicines.
- **Values:**
  - `null` means not stated, and unknown, absent and zero stay distinct.
  - Doses are strings, and zero is invalid.
  - "Once daily", "OD", "BD" and "TDS" are frequencies. A time slot is filled only from an explicit time.
- **Labels:** every report shows "SYNTHETIC DATA", and every draft shows "DRAFT, NOT APPROVED".
- **No answers leak in:** the pipeline never reads a case file's expected facts, medicines, evidence or flags. It reads only patient, doctor, date and encounter order.
- **Git:**
  - `runs/` is git-ignored, and nothing in it is committed.
  - Commit as AdityaRaj80 on the branch `aditya/extraction-report`.
  - No co-author or attribution lines in commit messages.

## Review Focus

1. **Quote matching is too strict:** a model quote differs from the transcript only in case, spacing or Unicode form, such as a precomposed `ज़` against `ज` plus a combining nukta. The item must be kept. Test: Task 5.
2. **Nothing clinical was said:** for a transcript like "Okay. Thank you.", the draft gets a blocking `nothing_extracted` issue, never an empty report that looks complete. Test: Task 7.
3. **HTML in text:** HTML in a record or model text, such as a patient name containing `<script>`, renders escaped in the HTML. Test: Task 12.
4. **No requests left mid-run:** if every provider and key runs out during a run, the run is marked incomplete at that stage. Earlier stages stay cached, and no report is written. Test: Task 14.
5. **Medicine name in Indian script:** the model returns a medicine name in Devanagari, such as "डोलो 650". It becomes `unmatched` with a blocking flag, and doesn't crash. Test: Task 3.

## Handoff to ASTRA

Aditya chose to have ASTRA build this plan, Native, while Claude's usage limit resets. Claude reviews the finished branch (runbook D-71).

**Read first, in this order:**
1. This plan, all of it, before writing any code. Every task's Interfaces block names what earlier and later tasks rely on.
2. The spec, `docs/superpowers/specs/2026-11-02-extraction-and-report-design.md`, for the reasons behind each rule.
3. `runbook.md`: decisions D-59 to D-71, judgement calls J-15 to J-18, corrections C-21 to C-31, and the open questions.

**The setup, already done:**
- The Python environment is `D:\Study\JANANI\.venv`, which is `../.venv` from the repo root.
- Ollama 0.40 runs as a Windows app with `qwen3:8b` and `qwen2.5:7b`. Its models are in `D:\Study\JANANI\models\ollama`. The location is set in the app's own settings, not by an environment variable, because the app ignores `OLLAMA_MODELS`.
- `.env` in the repo root holds `GEMINI_API_KEY`, `GEMINI_API_KEY_2`, `OLLAMA_MODEL=qwen3:8b` and `OLLAMA_HOST=http://localhost:11434`. It's git-ignored. Don't print its values.
- Typed scripts are in `data/eval/scripts`, and Whisper transcripts in `data/eval/results/whisper`.

**How to work:**
- Do the tasks in order, 0 to 16, with 10b after 10 and 14b after 14.
- Each task is test-first: write the test, see it fail for the stated reason, write the code, see it pass. Then run the whole suite, `../.venv/Scripts/python -m pytest services/api/tests tools -q`, before the commit.
- Use each task's commit message as written. One commit per task.
- No co-author, "Generated with" or other attribution lines in any commit, whether Claude, ASTRA or another tool.
- Task 0 makes one commit on `aditya/data-setup`. Every later commit goes on `aditya/extraction-report`. Don't push either branch, merge, or open a pull request until Aditya asks.
- Never weaken, skip or delete a test to make it pass. If a test in this plan looks wrong, stop, record why in the runbook as a correction (C-32 onwards), fix the test only if the spec supports the fix, and say so in the handoff note.
- Any change to a name, signature or value in an Interfaces block goes in the runbook as a decision (D-72 onwards), in the same commit.
- Live model calls happen only in Task 4 step 5 and Task 16. Everything else uses fakes, fixtures and the cache.
- If Gemini's daily limit runs out in Task 16, let the run fall back to the local model or wait for the reset. The cache keeps work already done.

**When finished, add a handoff note to the runbook's "What was done" table:**
- the branch, its last commit and the full test count
- for each task, done or not, and any step that didn't go as the plan said
- every deviation from the plan, with its runbook row
- the Task 16 numbers: blocking flags by case, the expected-flag check, and the Gemini and local comparison
- anything left unfinished, as an open question for Aditya

Claude then reviews the branch against this plan and the spec.

---

### Task 0: Commit pending work and branch

**Files:**
- Modify: `.gitignore` (add `runs/`)

- [x] **Step 1: Check that no key is in any file to be committed**

Run: `../.venv/Scripts/python -I tools/key_leak_check.py . ../Gemini_API.env.txt`, and again for `../Gemini_API(2).env.txt` and `../mistral_API.env.txt`. The script reads the key without printing it.
Expected: `files containing the key: 0` and `key in git history: False`, all three times

- [x] **Step 2: Run all existing tests**

Run: `../.venv/Scripts/python -m pytest tools/corpus/tests -q`
Expected: `128 passed`

- [x] **Step 3: Add `runs/` to `.gitignore`, then commit the audio tools, Whisper results, spec, plan, docs and runbook on `aditya/data-setup`**

```bash
git add .gitignore .env.example tools/corpus tools/key_leak_check.py data/eval/audio_index.csv data/eval/results data/README.md data/DOWNLOADS.md docs runbook.md
git commit -m "Add audio tools, Whisper results and the extraction design"
```

- [x] **Step 4: Create and switch to the working branch**

```bash
git switch -c aditya/extraction-report
```

---

### Task 1: Contracts and reference data

**Files:**
- Create: `services/api/requirements.txt`, which lists `pydantic>=2`, `pyyaml`, `jinja2`, `rapidfuzz`, `pypdf` and `pytest`
- Create: `services/api/tests/conftest.py`, which puts `services/api` on `sys.path` and exposes `REPO_ROOT`
- Create: `services/api/voicerx/contracts/medication.py`, `contracts/extraction.py`, `contracts/report.py`, `contracts/issues.py`
- Create: `services/api/voicerx/reference.py`
- Create: `data/rules/allergy_classes.yaml`
- Test: `services/api/tests/unit/test_contracts.py`

**Interfaces:**
- Produces, in `contracts/issues.py`:
  - `Issue(code: str, severity: Literal["block", "warn"], target: str, message: str)`
- Produces, in `contracts/medication.py`:
  - `Dose(amount: StrictStr, unit: str)`. The amount is a positive decimal written as text.
  - `Duration(value: int, unit: Literal["day", "week", "month"])`
  - `Frequency(type="frequency", times, period)`
  - `Grid(type="grid", m, a, e, n)`, with strings `"0"` or `"1"` and the like
  - `AsNeeded(type="as_needed", max_per_day: int | None)`
  - `TaperStep(dose, duration, when: Grid | None = None)` and `Taper(type="taper", steps)`. `when` is the step's time of day, when one is said.
  - `Schedule`, a discriminated union of the four schedule types
  - `Start(condition: Literal["unstated", "today", "tomorrow", "date"] = "unstated", date: date | None = None)`
  - `Food = Literal["before_food", "after_food", "with_food", "empty_stomach"]`
  - All models forbid extra fields.
- Produces, in `contracts/extraction.py`:
  - `ExtractedItem(id, kind, term, quote, assertion, certainty, temporality, laterality, subject, said_by)`. The kinds follow the spec's Stage 1 section. The value sets match `Fact` in `tools/corpus/case_schema.py`: `subject` is patient, family or other; `certainty` is stated, provisional or rule_out; `temporality` is current, past or planned. `said_by` is one of `"doctor"`, `"patient"` or `"unclear"`.
  - `ExtractedMedication(id, action, spoken_name, name_quote, dose_phrase, timing_phrase, food_phrase, duration_phrase, start_phrase, route_phrase, said_by)`. Every phrase is `str | None` and is quoted verbatim.
  - `ExtractedCorrection(target_id, field, old_quote, new_quote)`
  - `Extraction(items, medications, corrections)`
  - `DroppedItem(item: ExtractedItem, reason: str)`
  - `ResolvedMedication(id, action, spoken_name, match: Literal["exact", "ambiguous", "unmatched"], product_id: str | None, candidate_ids: list[str], dose: Dose | None, schedule: Schedule | None, food: Food | None, duration: Duration | None, start: Start, route: str | None, unresolved: list[str], quotes: dict[str, str], fuzzy: bool = False, speaker_unclear: bool = False, unbound: list[str] = [])`. `unbound` names the phrase fields that lay outside the medicine's own mention. Those values are left empty.
  - `CheckedExtraction(transcript_sha256, kept: list[ExtractedItem], dropped: list[DroppedItem], medications: list[ResolvedMedication], corrections: list[ExtractedCorrection], issues: list[Issue])`
- Produces, in `contracts/report.py`:
  - `MODEL_SECTIONS = ["chief_complaints", "history_present_illness", "vitals", "examination", "investigation_results", "investigations_ordered", "diagnoses", "advice", "referrals", "plan", "follow_up"]`
  - `ReportLine(text: str, cites: list[str])`
  - `ReportFields`, with one `list[ReportLine]` field per section in `MODEL_SECTIONS`, each defaulting to `[]`
  - `Header(clinic_name, doctor_name, doctor_reg_no, patient_name, sex, age, patient_id, mrn, visit_date: date, allergy_text)`
  - `MedicineRow(label, grid: list[str], detail, flags: list[str])`
  - `Resolution(id, action: Literal["choose_product", "set_dose", "set_timing", "set_food", "set_duration", "remove_medicine", "confirm_order", "acknowledge"], target: str, value: dict, reason: str, by: str, at: datetime)`
  - `DraftReport(case_id, status: Literal["draft"], version: int, predecessor_hash: str | None, header, sections: dict[str, list[ReportLine]], current_medicines: list[str], medicines: list[MedicineRow], not_discussed: list[str], checked: CheckedExtraction, issues: list[Issue], language_pref: str, record_snapshot: dict, products_used: dict[str, Product], resolutions: list[Resolution], content_hash: str)`. `record_snapshot` holds the `patient`, `doctor` and `clinic` records the draft used.
  - `ApprovedReport`, which has every `DraftReport` field, with `status: Literal["approved"]`, plus `approved_by: str` and `approved_at: datetime`. Its version is the draft's.
- Produces, in `reference.py`:
  - `Component(ingredient, strength: str, unit)`
  - `Product(id, brand, manufacturer, form, release_type, components, aliases)`
  - `Reference(products: dict[str, Product], patients: dict[str, dict], doctors: dict[str, dict], clinic: dict, allergy_classes: dict[str, list[str]], allergy_classes_reviewed: bool)`
  - `load_reference(repo_root: Path) -> Reference`
- `data/rules/allergy_classes.yaml`:

```yaml
reviewed: false
classes:
  penicillin: [amoxycillin, amoxicillin, ampicillin, cloxacillin, flucloxacillin, piperacillin, penicillin]
```

- [x] **Step 1: Write the failing tests**

```python
import pytest
from pydantic import ValidationError

from conftest import REPO_ROOT
from voicerx.contracts.medication import Dose
from voicerx.contracts.report import MODEL_SECTIONS, ReportFields
from voicerx.reference import load_reference


def test_zero_dose_is_rejected():
    with pytest.raises(ValidationError):
        Dose(amount="0", unit="tablet")


def test_half_dose_is_kept_exactly():
    assert Dose(amount="0.5", unit="tablet").amount == "0.5"


def test_numeric_dose_is_rejected():
    with pytest.raises(ValidationError):
        Dose(amount=0.5, unit="tablet")


def test_report_fields_reject_unknown_sections():
    with pytest.raises(ValidationError):
        ReportFields(current_medications=[])


def test_report_fields_have_every_model_section():
    assert set(ReportFields.model_fields) == set(MODEL_SECTIONS)


def test_reference_loads_products_patients_and_allergy_classes():
    reference = load_reference(REPO_ROOT)
    augmentin = reference.products["p-augmentin-625"]
    assert len(reference.products) == 25
    assert [(c.ingredient, c.strength, c.unit) for c in augmentin.components] == [
        ("Amoxycillin", "500", "mg"),
        ("Clavulanic Acid", "125", "mg"),
    ]
    assert reference.patients["pat-012"]["allergies"] == ["penicillin"]
    assert "amoxycillin" in reference.allergy_classes["penicillin"]
    assert reference.allergy_classes_reviewed is False
```

- [x] **Step 2: Run the tests to make sure they fail**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_contracts.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'voicerx.contracts.medication'`

- [x] **Step 3: Install the requirements, then implement the contracts and `load_reference`**

Run: `../.venv/Scripts/python -m pip install -r services/api/requirements.txt`. `load_reference` reads `data/formulary/products.csv` (`components` is JSON and `aliases` is separated by `;`), `data/seed/*.json` and `data/rules/allergy_classes.yaml`.

Also give the case format a taper time of day: add `when: Optional[Grid] = None` to `TaperStep` in `tools/corpus/case_schema.py`, and set `when: {type: grid, m: "1", a: "0", e: "0", "n": "0"}` on both `fam-010` taper steps. Then run `../.venv/Scripts/python tools/corpus/check_cases.py --write` and `../.venv/Scripts/python -m pytest tools/corpus/tests -q`.
Expected: no case errors, and `128 passed`

- [x] **Step 4: Run the tests to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_contracts.py -q`
Expected: `6 passed`

- [x] **Step 5: Commit**

```bash
git add services/api data/rules/allergy_classes.yaml tools/corpus/case_schema.py data/eval
git commit -m "Add report contracts and reference data loader"
```

---

### Task 2: Numbers and schedule parsing

**Files:**
- Create: `services/api/voicerx/pipeline/numbers.py`, `services/api/voicerx/pipeline/schedule.py`
- Test: `services/api/tests/unit/test_schedule.py`

**Interfaces:**
- Produces, in `numbers.py`: `words_to_digits(text: str) -> str`.
  - It case-folds the text and replaces runs of number words with digits, in English, Hindi, Tamil and Telugu.
  - A unit word followed by a tens word is spoken shorthand: "six fifty" is 650, and "one twenty eight" is 128.
  - "X hundred" and "X सौ" multiply by 100.
  - "point" makes a decimal.
  - Consecutive unit words stay separate: "one zero one" becomes `1 0 1`.
  - Half words are fractions: `आधा` and `आधी` are 0.5, and `डेढ़` is 1.5.
- Produces, in `schedule.py`:
  - `parse_dose(phrase: str | None) -> Dose | None`
  - `parse_timing(phrase: str | None) -> Schedule | None`
  - `parse_food(phrase: str | None) -> Food | None`
  - `parse_duration(phrase: str | None) -> Duration | None`
  - `parse_start(phrase: str | None, visit_date: date) -> Start`
  - Each returns `None` for text it can't parse, never a guess. `parse_start(None, …)` returns `Start(condition="unstated")`.

- [x] **Step 1: Write the failing tests**

```python
from datetime import date

import pytest

from voicerx.contracts.medication import AsNeeded, Dose, Duration, Frequency, Grid, Start, Taper
from voicerx.pipeline.numbers import words_to_digits
from voicerx.pipeline.schedule import parse_dose, parse_duration, parse_food, parse_start, parse_timing


@pytest.mark.parametrize("text, want", [
    ("Dolo six fifty", "dolo 650"),
    ("Augmentin six twenty five", "augmentin 625"),
    ("Azithral five hundred", "azithral 500"),
    ("Amlong two point five", "amlong 2.5"),
    ("BP today is one twenty eight over eighty two", "bp today is 128 over 82"),
    ("एक सौ साठ बटा सौ", "160 बटा 100"),
    ("one zero one", "1 0 1"),
    ("பத்து நாட்கள்", "10 நாட்கள்"),
    ("ఐదు రోజులు", "5 రోజులు"),
])
def test_number_words_become_digits(text, want):
    assert words_to_digits(text) == want


@pytest.mark.parametrize("phrase, want", [
    ("एक tablet", Dose(amount="1", unit="tablet")),
    ("one tablet", Dose(amount="1", unit="tablet")),
    ("एक गोली", Dose(amount="1", unit="tablet")),
    ("दो puff", Dose(amount="2", unit="puff")),
    ("दो चम्मच", Dose(amount="2", unit="teaspoon")),
    ("ஒரு tablet", Dose(amount="1", unit="tablet")),
    ("ఒక tablet", Dose(amount="1", unit="tablet")),
    ("आधी गोली", Dose(amount="0.5", unit="tablet")),
    ("1 टैबलेट", Dose(amount="1", unit="tablet")),
    (None, None),
    ("some", None),
])
def test_dose(phrase, want):
    assert parse_dose(phrase) == want


@pytest.mark.parametrize("phrase, want", [
    ("twice daily", Frequency(type="frequency", times=2, period="day")),
    ("once daily", Frequency(type="frequency", times=1, period="day")),
    ("OD", Frequency(type="frequency", times=1, period="day")),
    ("दिन में तीन बार", Frequency(type="frequency", times=3, period="day")),
    ("दिन में एक बार", Frequency(type="frequency", times=1, period="day")),
    ("రోజుకి రెండు సార్లు", Frequency(type="frequency", times=2, period="day")),
    ("सुबह", Grid(type="grid", m="1", a="0", e="0", n="0")),
    ("रात को", Grid(type="grid", m="0", a="0", e="0", n="1")),
    ("at night", Grid(type="grid", m="0", a="0", e="0", n="1")),
    ("सुबह और रात", Grid(type="grid", m="1", a="0", e="0", n="1")),
    ("one zero one", Grid(type="grid", m="1", a="0", e="0", n="1")),
    ("காலையில்", Grid(type="grid", m="1", a="0", e="0", n="0")),
    ("ज़रूरत पड़ने पर", AsNeeded(type="as_needed")),
    ("ज़रूरत पड़ने पर, दिन में चार बार से ज़्यादा नहीं", AsNeeded(type="as_needed", max_per_day=4)),
    ("now and then", None),
])
def test_timing(phrase, want):
    assert parse_timing(phrase) == want


def test_taper_has_one_step_per_dose():
    phrase = "पहले तीन दिन दो tablet सुबह खाने के बाद, फिर तीन दिन एक tablet सुबह खाने के बाद"
    taper = parse_timing(phrase)
    assert isinstance(taper, Taper)
    assert [(s.dose.amount, s.duration.value) for s in taper.steps] == [("2", 3), ("1", 3)]
    assert all(s.when == Grid(type="grid", m="1", a="0", e="0", n="0") for s in taper.steps)


@pytest.mark.parametrize("phrase, want", [
    ("after food", "after_food"), ("खाने के बाद", "after_food"), ("భోజనం తర్వాత", "after_food"),
    ("சாப்பாட்டுக்கு முன்", "before_food"), ("खाली पेट", "empty_stomach"), ("whenever", None),
])
def test_food(phrase, want):
    assert parse_food(phrase) == want


@pytest.mark.parametrize("phrase, want", [
    ("तीन दिन तक", Duration(value=3, unit="day")),
    ("for thirty days", Duration(value=30, unit="day")),
    ("दो हफ़्ते", Duration(value=2, unit="week")),
    ("एक महीने", Duration(value=1, unit="month")),
    ("பத்து நாட்கள்", Duration(value=10, unit="day")),
    ("ఐదు రోజులు", Duration(value=5, unit="day")),
    ("three days, not five", Duration(value=3, unit="day")),
    ("five days or three days", None),
])
def test_duration_keeps_months_and_refuses_ambiguity(phrase, want):
    assert parse_duration(phrase) == want


def test_start_tomorrow_resolves_from_the_visit_date():
    assert parse_start("from tomorrow", date(2026, 10, 5)) == Start(condition="tomorrow", date=date(2026, 10, 6))


def test_unstated_start_stays_unstated():
    assert parse_start(None, date(2026, 10, 5)) == Start(condition="unstated")
```

- [x] **Step 2: Run the tests to make sure they fail**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_schedule.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `numbers.py` and `schedule.py`**

**Approach:**
- Run `words_to_digits` first, then match small per-language tables of unit, slot, frequency, food and duration words.
- A correction ("X, not Y" in English, or "Y नहीं, X" in Hindi) yields X.
- Any other phrase with two different numbers returns `None`.

- [x] **Step 4: Run the tests to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_schedule.py -q`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add services/api/voicerx/pipeline services/api/tests/unit/test_schedule.py
git commit -m "Add number and schedule parsing"
```

---

### Task 3: Medicine matcher

**Files:**
- Create: `services/api/voicerx/pipeline/match_medicine.py`
- Test: `services/api/tests/unit/test_match_medicine.py`

**Interfaces:**
- Consumes: `Product` from Task 1 and `words_to_digits` from Task 2
- Produces: `MatchResult(match: Literal["exact", "ambiguous", "unmatched"], product_id: str | None, candidate_ids: list[str], fuzzy: bool = False)`, and `match_medicine(spoken: str, products: dict[str, Product], current_ids: frozenset[str] = frozenset()) -> MatchResult`

**Algorithm:**
1. **Normalise** the spoken name and every formulary name the same way: `words_to_digits`, case folding, hyphens to spaces, a space between digits and letters ("100mcg" becomes "100 mcg"), then drop form and unit words (tablet, tab, capsule, cap, inhaler, syrup, mg, mcg, ml). Compare whole tokens only. "2.5" is one token, so "5" never matches it.
2. **Group:** a product's names are its brand and each alias. The group is the products with a name whose first token equals the spoken first token. If the group is empty, use instead the products with a name whose first token scores `rapidfuzz.fuzz.ratio >= 85`, and mark the result fuzzy.
3. **Score:** let E be the spoken tokens after the first, and V a name's tokens after the first. A name fits when every token in E is in V or is one of the product's component strengths. A fitting name scores 3 when V equals E, 2 when V is a proper subset of E, and 1 otherwise. A product takes its best name's score.
4. **Decide** among the products with the top score:
   - A fuzzy result is ambiguous with those candidates, never exact.
   - One product is exact. At score 1, it's exact only if the group has one product, and otherwise ambiguous.
   - With several, the result is exact if exactly one of them is in `current_ids`, and otherwise ambiguous.
   - If no name fits, the result is unmatched.

For example, "Pan forty" scores 3 on Pan 40, but only 2 on Pan-D through its alias "Pan", because 40 is one of Pan-D's strengths. So Pan 40 wins.

- [x] **Step 1: Write the failing tests**

```python
import pytest

from conftest import REPO_ROOT
from voicerx.pipeline.match_medicine import match_medicine
from voicerx.reference import load_reference

PRODUCTS = load_reference(REPO_ROOT).products


@pytest.mark.parametrize("spoken, product_id", [
    ("Dolo six fifty", "p-dolo-650"), ("Pan forty", "p-pan-40"), ("Telma forty", "p-telma-40"),
    ("Amlong five", "p-amlong-5"), ("Amlong two point five", "p-amlong-2-5"), ("Atorva ten", "p-atorva-10"),
    ("Wysolone ten", "p-wysolone-10"), ("Asthalin inhaler", "p-asthalin-100"), ("Montair LC", "p-montair-lc"),
    ("Voveran fifty", "p-voveran-50"), ("Combiflam", "p-combiflam"),
    ("Augmentin six twenty five", "p-augmentin-625"), ("Azithral five hundred", "p-azithral-500"),
    ("Dolo 650", "p-dolo-650"), ("Amlong", "p-amlong-5"), ("Amlong 5", "p-amlong-5"),
    ("Telma H", "p-telma-h"), ("Pan D", "p-pan-d"), ("Pan-D", "p-pan-d"),
])
def test_exact_matches_from_the_case_scripts(spoken, product_id):
    result = match_medicine(spoken, PRODUCTS)
    assert (result.match, result.product_id) == ("exact", product_id)


def test_bare_pan_is_ambiguous_between_pan_40_and_pan_d():
    result = match_medicine("Pan", PRODUCTS)
    assert result.match == "ambiguous"
    assert result.product_id is None
    assert sorted(result.candidate_ids) == ["p-pan-40", "p-pan-d"]


def test_bare_pan_resolves_to_the_one_the_patient_is_taking():
    result = match_medicine("Pan", PRODUCTS, current_ids=frozenset({"p-pan-d"}))
    assert (result.match, result.product_id) == ("exact", "p-pan-d")


def test_misspelling_is_never_exact():
    result = match_medicine("Dollo 650", PRODUCTS)
    assert (result.match, result.candidate_ids, result.fuzzy) == ("ambiguous", ["p-dolo-650"], True)


def test_wrong_strength_is_unmatched():
    assert match_medicine("Dolo 500", PRODUCTS).match == "unmatched"


def test_brand_outside_the_formulary_is_unmatched():
    assert match_medicine("Mucaine gel", PRODUCTS).match == "unmatched"


def test_name_in_devanagari_is_unmatched_rather_than_guessed():
    result = match_medicine("डोलो 650", PRODUCTS)
    assert (result.match, result.product_id, result.candidate_ids) == ("unmatched", None, [])
```

- [x] **Step 2: Run the tests to make sure they fail**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_match_medicine.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `match_medicine` as described above**

- [x] **Step 4: Run the tests to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_match_medicine.py -q`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add services/api/voicerx/pipeline/match_medicine.py services/api/tests/unit/test_match_medicine.py
git commit -m "Add medicine matcher"
```

---

### Task 4: Model client, Gemini first and a local Ollama model as fallback

**Files:**
- Create: `services/api/voicerx/llm/__init__.py`, `services/api/voicerx/llm/client.py`, `services/api/voicerx/llm/gemini.py`, `services/api/voicerx/llm/ollama.py`
- Test: `services/api/tests/unit/test_llm.py`

**Interfaces:**
- Produces, in `client.py`:
  - `CallMeta(provider, model, prompt_version, cache_key, cached: bool, key_index: int, attempts: int)`
  - The exceptions `QuotaExhausted` and `ModelOutputInvalid`
  - `json_schema_for(model: type[BaseModel]) -> dict`. It inlines every `$ref`, removes `title` and `default`, and sets `additionalProperties: false`, with every property listed in `required`, on each object, so every field is always present in a reply.
  - `ModelClient(adapter, keys: list[str], cache_dir: Path, transport=None, sleep=time.sleep)`, with the method `generate(system: str, user: str, schema: type[BaseModel], prompt_version: str) -> tuple[BaseModel, CallMeta]`
  - `FallbackClient(clients: list[ModelClient])`, with the same `generate`. It moves to the next client on `QuotaExhausted`. Both keep their arguments as public attributes, `ModelClient.adapter` and `FallbackClient.clients`.
  - `build_client(env_path: Path, cache_dir: Path, only: Literal["gemini", "ollama"] | None = None) -> FallbackClient`. It uses Gemini with `GEMINI_API_KEY` and `GEMINI_API_KEY_2`, skipping any blank key, then Ollama when `OLLAMA_MODEL` is set. `OLLAMA_HOST` defaults to `http://localhost:11434`. `only` keeps one provider, for comparing them. It raises `ValueError` if no provider is left.
- The adapter interface has the attributes `name` and `model`, and three methods:
  - `build(system, user, schema: dict, key) -> tuple[str, dict[str, str], dict]`, returning the URL, headers and body
  - `reply_text(body: dict) -> str`
  - `is_quota_exhausted(status: int, headers: dict[str, str], text: str) -> bool`
- The transport signature is `transport(url: str, headers: dict[str, str], body: dict) -> tuple[int, dict[str, str], str]`. The default uses `urllib` with a 300-second timeout. It returns status `0` when the server can't be reached, and `ModelClient` treats status `0` as `QuotaExhausted` without retrying, for every adapter.
- In `gemini.py`, `GeminiAdapter(model="gemini-3.8-flash")`:
  - POSTs `https://generativelanguage.googleapis.com/v1beta/interactions` with `x-goog-api-key: <key>`.
  - The body is `{"model", "input": [{"type": "user_input", "content": [{"type": "text", "text": system + "\n\n" + user}]}], "response_format": {"type": "text", "mime_type": "application/json", "schema": …}}`.
  - The reply is the last JSON text in the `model_output` step.
  - Quota is exhausted on a 429 whose text contains "per day".
- In `ollama.py`, `OllamaAdapter(model="qwen3:8b", host="http://localhost:11434")`:
  - Its `name` is `"ollama"`. `build_client` passes it the key list `["local"]`, and the key is never sent.
  - POSTs `<host>/api/chat` with only `Content-Type: application/json`.
  - The body is `{"model", "stream": false, "think": false, "format": <schema>, "options": {"temperature": 0, "num_ctx": 8192}, "messages": [system, user]}`. `think: false` turns off Qwen 3's thinking text, which would otherwise come before the JSON. An 8192-token context keeps the model fully on the 8 GB GPU; 16384 pushed 20% onto the CPU and ran at 10 instead of 16.5 tokens a second (runbook C-30).
  - The reply is `message.content`. `reply_text` raises `ValueError` unless `done_reason` is `"stop"`, or when `prompt_eval_count + eval_count` reaches `num_ctx`, because Ollama cuts a prompt or reply that overflows the context without saying so. `ModelClient` treats that `ValueError` like an invalid reply: one repair attempt, then `ModelOutputInvalid`.
  - Quota is exhausted on a 404, which Ollama sends when the model isn't pulled.
- **Cache:**
  - The file is `cache_dir/<cache_key>.json`. `cache_key` is the SHA-256 of provider, model, prompt version, system and user.
  - It holds only the reply text and the `CallMeta` fields, never a key.
- **Retries:**
  - On another 429, a 503 or another 5xx, wait for `Retry-After`, otherwise `20 × attempt` seconds, and retry, up to 6 attempts. If all 6 fail, raise `QuotaExhausted` so that `FallbackClient` moves on.
  - If the reply fails Pydantic validation, send one repair request. If that also fails, raise `ModelOutputInvalid`.

- [x] **Step 1: Write the failing tests**

```python
import json

import pytest
from pydantic import BaseModel

from voicerx.llm.client import (FallbackClient, ModelClient, ModelOutputInvalid, QuotaExhausted, build_client,
                                json_schema_for)
from voicerx.llm.gemini import GeminiAdapter
from voicerx.llm.ollama import OllamaAdapter


class Inner(BaseModel):
    word: str


class Outer(BaseModel):
    items: list[Inner]


def ollama_reply(obj, done_reason="stop", used=500):
    return 200, {}, json.dumps({"message": {"role": "assistant", "content": json.dumps(obj)},
                                "done_reason": done_reason, "prompt_eval_count": used, "eval_count": 100})


def gemini_reply(obj):
    return 200, {}, json.dumps({"steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(obj)}]}]})


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        return self.responses.pop(0)


def gemini(tmp_path, responses, keys=("g1",)):
    transport = FakeTransport(responses)
    return ModelClient(GeminiAdapter(), list(keys), tmp_path, transport=transport, sleep=lambda s: None), transport


def ollama(tmp_path, responses):
    transport = FakeTransport(responses)
    return ModelClient(OllamaAdapter(), ["local"], tmp_path, transport=transport, sleep=lambda s: None), transport


DAILY_LIMIT = (429, {}, '{"error": {"message": "Quota exceeded for requests per day"}}')


def test_schema_is_strict_and_has_no_references():
    schema = json_schema_for(Outer)
    item = schema["properties"]["items"]["items"]
    assert "$ref" not in json.dumps(schema)
    assert item["additionalProperties"] is False and item["required"] == ["word"]


def test_gemini_request_uses_the_interactions_api_with_a_schema():
    url, headers, body = GeminiAdapter().build("s", "u", json_schema_for(Outer), "g1")
    assert url.endswith("/v1beta/interactions") and headers["x-goog-api-key"] == "g1"
    assert body["response_format"]["mime_type"] == "application/json"


def test_ollama_request_enforces_the_schema_and_sends_no_key():
    url, headers, body = OllamaAdapter().build("s", "u", json_schema_for(Outer), "local")
    assert url == "http://localhost:11434/api/chat"
    assert "local" not in json.dumps(headers) and "Authorization" not in headers
    assert body["format"] == json_schema_for(Outer)
    assert body["stream"] is False and body["think"] is False and body["options"]["temperature"] == 0


def test_second_identical_call_is_served_from_the_cache(tmp_path):
    client, transport = gemini(tmp_path, [gemini_reply({"items": [{"word": "a"}]})])
    client.generate("s", "u", Outer, "v1")
    result, meta = client.generate("s", "u", Outer, "v1")
    assert result.items[0].word == "a" and meta.cached is True and len(transport.calls) == 1


def test_daily_limit_moves_to_the_second_key_without_retrying(tmp_path):
    client, transport = gemini(tmp_path, [DAILY_LIMIT, gemini_reply({"items": []})], keys=("g1", "g2"))
    _, meta = client.generate("s", "u", Outer, "v1")
    assert meta.key_index == 1 and len(transport.calls) == 2


def test_overloaded_provider_is_retried(tmp_path):
    client, transport = gemini(tmp_path, [(503, {}, "busy"), gemini_reply({"items": []})])
    _, meta = client.generate("s", "u", Outer, "v1")
    assert meta.attempts == 2


def test_fallback_moves_from_gemini_to_ollama(tmp_path):
    first, _ = gemini(tmp_path / "g", [DAILY_LIMIT])
    local, _ = ollama(tmp_path / "o", [ollama_reply({"items": []})])
    _, meta = FallbackClient([first, local]).generate("s", "u", Outer, "v1")
    assert meta.provider == "ollama"


def test_unreachable_server_is_exhausted_immediately(tmp_path):
    client, transport = ollama(tmp_path, [(0, {}, "connection refused")])
    with pytest.raises(QuotaExhausted):
        client.generate("s", "u", Outer, "v1")
    assert len(transport.calls) == 1


def test_model_not_pulled_is_exhausted_immediately(tmp_path):
    client, transport = ollama(tmp_path, [(404, {}, '{"error":"model \'qwen3:8b\' not found"}')])
    with pytest.raises(QuotaExhausted):
        client.generate("s", "u", Outer, "v1")
    assert len(transport.calls) == 1


def test_cut_off_or_overflowing_reply_is_never_accepted(tmp_path):
    client, _ = ollama(tmp_path, [ollama_reply({"items": []}, done_reason="length"),
                                  ollama_reply({"items": []}, used=8100)])
    with pytest.raises(ModelOutputInvalid):
        client.generate("s", "u", Outer, "v1")


def test_invalid_reply_gets_one_repair_attempt(tmp_path):
    client, _ = ollama(tmp_path, [ollama_reply({"wrong": 1}), ollama_reply({"items": []})])
    result, meta = client.generate("s", "u", Outer, "v1")
    assert result.items == [] and meta.attempts == 2


def test_two_invalid_replies_raise(tmp_path):
    client, _ = ollama(tmp_path, [ollama_reply({"wrong": 1}), ollama_reply({"wrong": 2})])
    with pytest.raises(ModelOutputInvalid):
        client.generate("s", "u", Outer, "v1")


def test_cache_files_never_contain_a_key(tmp_path):
    client, _ = gemini(tmp_path, [gemini_reply({"items": []})], keys=("SECRET-KEY-VALUE",))
    client.generate("s", "u", Outer, "v1")
    assert all("SECRET-KEY-VALUE" not in p.read_text(encoding="utf-8") for p in tmp_path.glob("*.json"))


def test_build_client_orders_gemini_before_ollama_and_can_keep_one(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=g1\nGEMINI_API_KEY_2=\nOLLAMA_MODEL=qwen3:8b\n", encoding="utf-8")
    assert [c.adapter.name for c in build_client(env, tmp_path).clients] == ["gemini", "ollama"]
    assert [c.adapter.name for c in build_client(env, tmp_path, only="ollama").clients] == ["ollama"]
```

- [x] **Step 2: Run the tests to make sure they fail**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_llm.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `client.py`, `gemini.py` and `ollama.py` as specified above**

- [x] **Step 4: Run the tests to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_llm.py -q`
Expected: all pass

- [x] **Step 5: Check each provider's request shape with one live call**

Run one `generate` call per provider with a tiny schema, through `build_client(Path(".env"), Path("runs/cache"), only="gemini")` and then `only="ollama"`. The Ollama app must be running; `ollama list` shows `qwen3:8b`.
Expected: a valid parsed object from each, with no key in the output. If a field is rejected, fix the adapter and record the change in the runbook.

- [x] **Step 6: Commit**

```bash
git add services/api/voicerx/llm services/api/tests/unit/test_llm.py
git commit -m "Add model client: Gemini first, local Ollama fallback, cache and one repair attempt"
```

---

### Task 5: Check 1

**Files:**
- Create: `services/api/voicerx/pipeline/check_extraction.py`
- Test: `services/api/tests/unit/test_check_extraction.py`

**Interfaces:**
- Consumes: the Task 1 contracts and `Reference`, the Task 2 parsers, and the Task 3 `match_medicine`
- Produces: `check_extraction(extraction: Extraction, transcript: str, reference: Reference, patient_id: str, visit_date: date, current_ids: frozenset[str] = frozenset()) -> CheckedExtraction`

**Issue codes:**

| Code | Severity |
|---|---|
| `quote_not_found` | warn, and the item is dropped |
| `patient_speech` | warn, and an exam item or medicine said by the patient is dropped |
| `speaker_unclear` | block for a medicine, warn for an exam item. Raised when `said_by` is `unclear`, or when the sentence holding the quote has a first-person word: मैं, मुझे, मेरा, मेरी, I, my, me, నేను, నా, நான், என் |
| `phrase_not_bound` | block. A medicine's phrase, or a correction to it, lies outside the medicine's own mention. The phrase isn't used. |
| `negation_mismatch` | block |
| `laterality_mismatch` | block |
| `unparsed_dose`, `unparsed_timing`, `unparsed_food`, `unparsed_duration` | warn |
| `missing_quantity` | block, for action `start`, `change` or `continue` with no dose. A taper is exempt when every step has a dose. |
| `ambiguous_product` | block |
| `fuzzy_product_match` | block, in place of `ambiguous_product` when the name was found only by fuzzy spelling |
| `unmatched_product` | block |
| `allergy_conflict` | block |

**How the checks work:**
- Quotes are compared after NFC normalisation, case folding and collapsing whitespace.
- The negation cues are the words in `tools/corpus/check_cases.py` `NEGATION_WORDS`, copied into this module.
- A correction targeting a medicine field replaces that field's phrase with the correction's `new_quote` before parsing.
- **A medicine's mention** runs from its name quote to the earliest of three points: the sentence end (`।`, `?`, `!`, a newline, or a `.` followed by a space or the end), the next medicine's name quote, or 200 characters. When the name occurs more than once, use the first occurrence whose mention holds all the phrases. A correction's `new_quote` may run past the sentence end, but must come before the next medicine's name.
- Also export `medicine_issues(medications: list[ResolvedMedication], reference: Reference, allergies: list[str] | None) -> list[Issue]`. It raises the medicine codes from the resolved values and stored flags alone, without the transcript, so Task 10b can re-run it. Those codes are `missing_quantity`, the three product codes, `allergy_conflict`, `unparsed_*` from `unresolved`, and `speaker_unclear` and `phrase_not_bound` from the stored flags.

- [x] **Step 1: Write the failing tests**

```python
from datetime import date

from conftest import REPO_ROOT
from voicerx.contracts.extraction import Extraction, ExtractedCorrection, ExtractedItem, ExtractedMedication
from voicerx.contracts.medication import Dose, Duration, Frequency, Taper
from voicerx.pipeline.check_extraction import check_extraction
from voicerx.reference import load_reference

REF = load_reference(REPO_ROOT)
VISIT = date(2026, 10, 5)
TRANSCRIPT = "Pain in the left wrist. No fever. Dolo six fifty, one tablet twice daily after food for three days."


def item(**changes):
    base = dict(id="x1", kind="symptom", term="fever", quote="No fever", assertion="absent", certainty="stated",
                temporality="current", laterality=None, subject="patient", said_by="doctor")
    return ExtractedItem(**{**base, **changes})


def med(**changes):
    base = dict(id="rx1", action="start", spoken_name="Dolo six fifty", name_quote="Dolo six fifty",
                dose_phrase="one tablet", timing_phrase="twice daily", food_phrase="after food",
                duration_phrase="for three days", start_phrase=None, route_phrase=None, said_by="doctor")
    return ExtractedMedication(**{**base, **changes})


def run(items=(), meds=(), corrections=(), transcript=TRANSCRIPT, patient="pat-001"):
    extraction = Extraction(items=list(items), medications=list(meds), corrections=list(corrections))
    return check_extraction(extraction, transcript, REF, patient, VISIT)


def codes(checked):
    return {i.code for i in checked.issues}


def test_clean_extraction_keeps_everything_and_resolves_the_medicine():
    checked = run([item()], [med()])
    assert [i.id for i in checked.kept] == ["x1"]
    rx = checked.medications[0]
    assert (rx.match, rx.product_id) == ("exact", "p-dolo-650")
    assert rx.dose == Dose(amount="1", unit="tablet")
    assert rx.schedule == Frequency(type="frequency", times=2, period="day")
    assert (rx.food, rx.duration) == ("after_food", Duration(value=3, unit="day"))
    assert codes(checked) == set()


def test_quote_missing_from_the_transcript_drops_the_item():
    checked = run([item(quote="High fever")])
    assert checked.kept == [] and checked.dropped[0].reason == "quote_not_found"


def test_quote_with_different_case_and_spacing_is_kept():
    assert [i.id for i in run([item(quote="no   FEVER")]).kept] == ["x1"]


def test_unicode_form_of_a_quote_does_not_drop_it():
    transcript = "बुखार नहीं है। ज़ुकाम है।"
    decomposed = "ज़ुकाम है"
    checked = run([item(id="x2", term="cold", quote=decomposed, assertion="present")], transcript=transcript)
    assert [i.id for i in checked.kept] == ["x2"]


def test_absent_item_quoted_without_negation_blocks():
    assert "negation_mismatch" in codes(run([item(quote="fever", assertion="absent")],
                                            transcript="Mild fever since morning."))


def test_wrong_side_blocks():
    assert "laterality_mismatch" in codes(run([item(term="wrist pain", quote="Pain in the left wrist",
                                                    assertion="present", laterality="right")]))


def test_exam_finding_said_by_the_patient_is_dropped():
    checked = run([item(kind="exam", term="wrist pain", quote="Pain in the left wrist",
                        assertion="present", said_by="patient")])
    assert checked.kept == [] and "patient_speech" in codes(checked)


def test_missing_dose_on_a_new_medicine_blocks():
    assert "missing_quantity" in codes(run(meds=[med(dose_phrase=None)]))


def test_bare_pan_blocks_as_ambiguous():
    checked = run(meds=[med(spoken_name="Pan", name_quote="Pan", dose_phrase="एक गोली", timing_phrase="सुबह",
                            food_phrase=None, duration_phrase=None)], transcript="Pan एक गोली सुबह।")
    assert "ambiguous_product" in codes(checked)


def test_penicillin_allergy_with_augmentin_blocks():
    transcript = "Augmentin six twenty five, ఒక tablet."
    checked = run(meds=[med(spoken_name="Augmentin six twenty five", name_quote="Augmentin six twenty five",
                            dose_phrase="ఒక tablet", timing_phrase=None, food_phrase=None, duration_phrase=None)],
                  transcript=transcript, patient="pat-012")
    assert "allergy_conflict" in codes(checked)


def test_correction_replaces_the_duration_before_parsing():
    transcript = "Combiflam, one tablet twice daily after food for five days, sorry, three days, not five."
    checked = run(meds=[med(spoken_name="Combiflam", name_quote="Combiflam", duration_phrase="for five days")],
                  corrections=[ExtractedCorrection(target_id="rx1", field="duration_phrase",
                                                   old_quote="for five days", new_quote="three days, not five")],
                  transcript=transcript)
    assert checked.medications[0].duration == Duration(value=3, unit="day")


def test_dose_from_another_sentence_is_not_borrowed():
    transcript = "Dolo six fifty after food for three days. Pan forty, one tablet in the morning."
    checked = run(meds=[med(timing_phrase=None)], transcript=transcript)
    assert "phrase_not_bound" in codes(checked) and checked.medications[0].dose is None


def test_continued_medicine_without_a_dose_blocks():
    assert "missing_quantity" in codes(run(meds=[med(action="continue", dose_phrase=None)]))


def test_taper_with_a_dose_in_every_step_is_not_missing_a_quantity():
    taper = "पहले तीन दिन दो tablet सुबह खाने के बाद, फिर तीन दिन एक tablet सुबह खाने के बाद"
    checked = run(meds=[med(spoken_name="Wysolone ten", name_quote="Wysolone ten", dose_phrase=None,
                            timing_phrase=taper, food_phrase="खाने के बाद", duration_phrase=None)],
                  transcript=f"Wysolone ten, {taper}।")
    assert isinstance(checked.medications[0].schedule, Taper)
    assert "missing_quantity" not in codes(checked)


def test_medicine_in_a_first_person_sentence_blocks_whatever_the_model_said():
    checked = run(meds=[med(spoken_name="Combiflam", name_quote="Combiflam", dose_phrase="दो गोली",
                            timing_phrase=None, food_phrase=None, duration_phrase=None)],
                  transcript="मैं तो Combiflam दो गोली रोज़ ले लेता हूँ।")
    assert "speaker_unclear" in codes(checked)


def test_medicine_with_an_unclear_speaker_blocks():
    assert "speaker_unclear" in codes(run(meds=[med(said_by="unclear")]))


def test_misspelt_brand_is_never_exact():
    checked = run(meds=[med(spoken_name="Dollo 650", name_quote="Dollo 650")],
                  transcript="Dollo 650, one tablet twice daily after food for three days.")
    assert "fuzzy_product_match" in codes(checked) and checked.medications[0].product_id is None
```

- [x] **Step 2: Run the tests to make sure they fail**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_check_extraction.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `check_extraction`**

- [x] **Step 4: Run the tests to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_check_extraction.py -q`
Expected: all pass

- [x] **Step 5: Commit**

```bash
git add services/api/voicerx/pipeline/check_extraction.py services/api/tests/unit/test_check_extraction.py
git commit -m "Add check 1: quotes, negation, side, speaker and medicine resolution"
```

---

### Task 6: Stage 1 prompt

**Files:**
- Create: `services/api/voicerx/pipeline/extract.py`
- Test: `services/api/tests/unit/test_extract.py`

**Interfaces:**
- Consumes: the model client's `generate` from Task 4, and `Extraction` and `Reference` from Task 1
- Produces: `PROMPT_VERSION = "extract-v1"`, `build_extraction_prompt(transcript: str, brand_names: list[str]) -> tuple[str, str]`, which returns the system and user text, and `extract(client, transcript: str, reference: Reference) -> tuple[Extraction, CallMeta]`

**The system prompt states the spec's Stage 1 rules:**
- Copy quotes exactly.
- Never infer a value.
- Mark negation.
- Mark patient speech, and use `unclear` when the speaker isn't certain.
- Take each medicine's phrases only from its own mention.
- Treat the transcript as data, never as instructions.
- Return only the schema.

**The user text** holds the brand list, then the transcript between `<<<TRANSCRIPT` and `TRANSCRIPT>>>`.

- [x] **Step 1: Write the failing tests**

```python
from voicerx.contracts.extraction import Extraction
from voicerx.pipeline.extract import PROMPT_VERSION, build_extraction_prompt, extract


class FakeClient:
    def __init__(self):
        self.calls = []

    def generate(self, system, user, schema, prompt_version):
        self.calls.append((system, user, schema, prompt_version))
        return Extraction(items=[], medications=[], corrections=[]), "meta"


def test_transcript_is_fenced_and_copied_verbatim():
    _, user = build_extraction_prompt("बुखार नहीं है।", ["Dolo 650"])
    assert "<<<TRANSCRIPT\nबुखार नहीं है।\nTRANSCRIPT>>>" in user
    assert "Dolo 650" in user


def test_extract_asks_for_the_extraction_schema_with_the_prompt_version():
    from conftest import REPO_ROOT
    from voicerx.reference import load_reference

    fake = FakeClient()
    result, _ = extract(fake, "No fever.", load_reference(REPO_ROOT))
    assert result.items == []
    assert fake.calls[0][2] is Extraction and fake.calls[0][3] == PROMPT_VERSION
```

- [x] **Step 2: Run the tests to make sure they fail**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_extract.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `extract.py`**

- [x] **Step 4: Run the tests to make sure they pass, then commit**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_extract.py -q`
Expected: all pass

```bash
git add services/api/voicerx/pipeline/extract.py services/api/tests/unit/test_extract.py
git commit -m "Add stage 1 extraction prompt"
```

---

### Task 7: Check 2

**Files:**
- Create: `services/api/voicerx/pipeline/check_report.py`
- Test: `services/api/tests/unit/test_check_report.py`

**Interfaces:**
- Consumes: `ReportFields`, `CheckedExtraction` and `Reference` from Task 1, and `words_to_digits` from Task 2
- Produces: `SECTION_KINDS: dict[str, set[str]]`, and `check_report(fields: ReportFields, checked: CheckedExtraction, reference: Reference) -> list[Issue]`

**Section kinds:**

| Section | Kinds allowed |
|---|---|
| `chief_complaints` | symptom |
| `history_present_illness` | symptom, history, family_history, allergy |
| `vitals` | vital |
| `examination` | exam |
| `investigation_results` | result |
| `investigations_ordered` | order |
| `diagnoses` | diagnosis |
| `advice` | advice |
| `referrals` | referral |
| `plan` | plan |
| `follow_up` | follow_up |

**Issue codes:**

| Code | Severity | Fails when |
|---|---|---|
| `line_unsupported` | block | A line has no citation, or cites an unknown id |
| `number_not_in_source` | block | The line's numbers, after `words_to_digits`, aren't all in the cited items' terms and quotes |
| `medicine_not_in_source` | block | A formulary brand or alias in the line doesn't appear in a cited item |
| `dose_in_text` | block | The line contains `\b\d+(\.\d+)?\s?(mg\|mcg\|ml\|tablets?\|tabs?\|capsules?\|puffs?)\b` (the `\|` is GitHub table escaping; the regex uses plain `|`) |
| `negation_mismatch` | block | Every cited item is absent and the line has no negation cue (no, not, denies, denied, negative, absent, nil, without, none). Or every cited item is present, the line has a cue, and no cited quote has one of Check 1's negation words, so "Review if not better in 3 days" passes when its quote is conditional too. |
| `mixed_negation` | block | A line cites both absent and present items |
| `subject_mismatch` | block | A cited item's subject is family or other and the line names no relative (family, mother, father, brother, sister, son, daughter, wife, husband, parent, relative), or every cited item is the patient's and the line names one |
| `certainty_mismatch` | block | A cited item is provisional and the line lacks "provisional", "suspected", "probable" and "likely"; a cited item is rule_out and the line lacks "rule out"; or every cited item is stated and the line has one of those words |
| `temporality_mismatch` | warn | A cited item is past and the line lacks "history of", "known", "past", "previous", "earlier", "since" and "ago" |
| `laterality_mismatch` | block | A cited item's side word (left, right, bilateral or both) is missing from the line |
| `section_mismatch` | warn | |
| `omission` | block | A kept item is cited by no line |
| `duplication` | warn | A kept item is cited by more than one line |
| `nothing_extracted` | block | There are no kept items and no medicines |

- [x] **Step 1: Write the failing tests**

```python
from conftest import REPO_ROOT
from voicerx.contracts.extraction import CheckedExtraction, ExtractedItem
from voicerx.contracts.report import ReportFields, ReportLine
from voicerx.pipeline.check_report import check_report
from voicerx.reference import load_reference

REF = load_reference(REPO_ROOT)


def item(id, kind, term, quote, assertion="present", laterality=None, subject="patient", certainty="stated",
         temporality="current"):
    return ExtractedItem(id=id, kind=kind, term=term, quote=quote, assertion=assertion, certainty=certainty,
                         temporality=temporality, laterality=laterality, subject=subject, said_by="doctor")


CHECKED = CheckedExtraction(
    transcript_sha256="x", dropped=[], medications=[], corrections=[], issues=[],
    kept=[item("x1", "symptom", "sore throat for three days", "तीन दिन से गले में दर्द"),
          item("x2", "symptom", "fever", "बुखार नहीं है", assertion="absent"),
          item("x3", "exam", "swelling over the left wrist", "swelling over the left wrist", laterality="left")])


def fields(**sections):
    base = {"chief_complaints": [ReportLine(text="Sore throat for 3 days", cites=["x1"])],
            "history_present_illness": [ReportLine(text="No fever", cites=["x2"])],
            "examination": [ReportLine(text="Swelling over the left wrist", cites=["x3"])]}
    return ReportFields(**{**base, **sections})


def codes(f, checked=CHECKED):
    return {i.code for i in check_report(f, checked, REF)}


def test_faithful_report_has_no_issues():
    assert codes(fields()) == set()


def test_line_without_citations_blocks():
    assert "line_unsupported" in codes(fields(advice=[ReportLine(text="Rest", cites=[])]))


def test_number_not_in_the_cited_item_blocks():
    assert "number_not_in_source" in codes(fields(chief_complaints=[ReportLine(text="Sore throat for 5 days", cites=["x1"])]))


def test_negation_lost_in_writing_blocks():
    assert "negation_mismatch" in codes(fields(history_present_illness=[ReportLine(text="Fever", cites=["x2"])]))


def test_side_lost_in_writing_blocks():
    assert "laterality_mismatch" in codes(fields(examination=[ReportLine(text="Swelling over the wrist", cites=["x3"])]))


def test_dose_written_into_a_section_blocks():
    assert "dose_in_text" in codes(fields(advice=[ReportLine(text="Take 2 tablets", cites=["x1"])]))


def test_medicine_named_without_a_source_blocks():
    assert "medicine_not_in_source" in codes(fields(advice=[ReportLine(text="Avoid Combiflam", cites=["x1"])]))


def test_finding_filed_under_the_wrong_section_warns():
    assert "section_mismatch" in codes(fields(examination=[], vitals=[ReportLine(text="Swelling over the left wrist", cites=["x3"])]))


def test_item_never_cited_is_an_omission():
    assert "omission" in codes(fields(examination=[]))


def test_item_cited_twice_is_duplication():
    assert "duplication" in codes(fields(history_present_illness=[ReportLine(text="No fever", cites=["x2"]),
                                                                  ReportLine(text="Denies fever", cites=["x2"])]))


def test_empty_extraction_blocks_instead_of_looking_complete():
    empty = CHECKED.model_copy(update={"kept": []})
    assert "nothing_extracted" in codes(ReportFields(), empty)


def plus(*items):
    return CHECKED.model_copy(update={"kept": CHECKED.kept + list(items)})


def test_line_mixing_absent_and_present_items_blocks():
    line = ReportLine(text="Sore throat for 3 days, no fever", cites=["x1", "x2"])
    assert "mixed_negation" in codes(fields(chief_complaints=[line], history_present_illness=[]))


def test_relatives_condition_written_as_the_patients_blocks():
    checked = plus(item("x4", "family_history", "diabetes in mother", "माँ को sugar है", subject="family"))
    hpi = [ReportLine(text="No fever", cites=["x2"])]
    wrong = fields(history_present_illness=hpi + [ReportLine(text="Diabetes", cites=["x4"])])
    right = fields(history_present_illness=hpi + [ReportLine(text="Mother has diabetes", cites=["x4"])])
    assert "subject_mismatch" in codes(wrong, checked)
    assert "subject_mismatch" not in codes(right, checked)


def test_provisional_diagnosis_written_as_confirmed_blocks():
    checked = plus(item("x5", "diagnosis", "viral pharyngitis", "viral pharyngitis लग रहा है", certainty="provisional"))
    wrong = fields(diagnoses=[ReportLine(text="Viral pharyngitis", cites=["x5"])])
    right = fields(diagnoses=[ReportLine(text="Provisional: viral pharyngitis", cites=["x5"])])
    assert "certainty_mismatch" in codes(wrong, checked)
    assert "certainty_mismatch" not in codes(right, checked)


def test_past_history_written_as_current_warns():
    checked = plus(item("x6", "history", "asthma for five years", "Known asthma है, पाँच साल से", temporality="past"))
    hpi = [ReportLine(text="No fever", cites=["x2"]), ReportLine(text="Asthma", cites=["x6"])]
    assert "temporality_mismatch" in codes(fields(history_present_illness=hpi), checked)


def test_conditional_follow_up_keeps_its_negation():
    checked = plus(item("x7", "follow_up", "come back if not better in three days",
                        "तीन दिन में ठीक न हो तो दोबारा दिखाना है", temporality="planned"))
    line = ReportLine(text="Review if not better in 3 days", cites=["x7"])
    assert "negation_mismatch" not in codes(fields(follow_up=[line]), checked)
```

- [x] **Step 2: Run the tests to make sure they fail**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_check_report.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `check_report` as specified above**

- [x] **Step 4: Run the tests to make sure they pass, then commit**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_check_report.py -q`
Expected: all pass

```bash
git add services/api/voicerx/pipeline/check_report.py services/api/tests/unit/test_check_report.py
git commit -m "Add check 2: every report line must match what it cites"
```

---

### Task 8: Draft assembly

**Files:**
- Create: `services/api/voicerx/pipeline/assemble.py`
- Test: `services/api/tests/unit/test_assemble.py`

**Interfaces:**
- Consumes: the Tasks 1, 5 and 7 outputs
- Produces:
  - `product_label(product: Product) -> str`
  - `medicine_row(rx: ResolvedMedication, reference: Reference, visit_date: date) -> MedicineRow`
  - `table_medicines(checked: CheckedExtraction) -> list[ResolvedMedication]`, which returns the medicines with action `start`, `change` or `continue`, in order
  - `current_medicine_lines(checked: CheckedExtraction, reference: Reference) -> list[str]`
  - `build_header(patient_id, doctor_id, visit_date, reference) -> Header`
  - `assemble_draft(case_id, patient_id, doctor_id, visit_date, fields, checked, check2_issues, reference) -> DraftReport`. It sets `version=1`, `predecessor_hash=None` and `resolutions=[]`. It copies the patient, doctor and clinic records into `record_snapshot`, and every product that the table, the current list or a candidate names into `products_used`.
  - `content_hash(report: DraftReport | ApprovedReport) -> str`

**Fixed wording:**

| Field | Wording |
|---|---|
| Label | `{BRAND} {FORM} ({ING+ING}) {S1UNIT+S2UNIT}`, uppercase. The form is TAB for tablet, CAP for capsule and INHALER for inhaler. |
| Ambiguous label | `Doctor to choose: {label} or {label}` |
| Unmatched label | `Unrecognised medicine: {spoken_name}` |
| Grid | Grid values for a `Grid`, otherwise `["-", "-", "-", "-"]` |
| Detail line | Comma-joined, first letter capitalised: dose ("1 tablet", or "quantity not stated"), timing when not a grid ("once daily, time not specified", "twice daily, times not specified", "3 times a day, times not specified", "when needed", "when needed, at most 4 a day", a taper's steps, or "timing not stated"), food ("after food", "before food", "empty stomach", "with food", or "food timing not stated"), duration ("for 3 days", "for 2 weeks", "for 1 month", or "duration not stated"), and start ("start not stated", or `from 06-Oct-2026 (TUE)`) |
| Taper | Each step as `{dose} {time} for {duration}`, joined by ", then ", such as "2 tablets in the morning for 3 days, then 1 tablet in the morning for 3 days". The time is "in the morning", "in the afternoon", "in the evening" or "at night", joined by " and ", and is left out when the step has none. A taper's detail line has no separate dose or duration part. |
| Current medicines | `Continuing: {label}` for continue, `Past: {label}` for history, or `Stopped: {label}` for stop. A continued medicine is also in the table. |
| Allergy text | `Known allergies: penicillin`, `No known allergies` or `Allergy status not recorded` |
| Not discussed | Display names of the empty model sections, in `MODEL_SECTIONS` order |
| Content hash | SHA-256 of the report's canonical JSON, without `content_hash`, `status`, `approved_by` and `approved_at` |

- [x] **Step 1: Write the failing tests**

```python
from datetime import date

from conftest import REPO_ROOT
from voicerx.contracts.extraction import ResolvedMedication
from voicerx.contracts.extraction import CheckedExtraction
from voicerx.contracts.medication import AsNeeded, Dose, Duration, Frequency, Grid, Start, Taper, TaperStep
from voicerx.pipeline.assemble import (build_header, current_medicine_lines, medicine_row, product_label,
                                       table_medicines)
from voicerx.reference import load_reference

REF = load_reference(REPO_ROOT)
VISIT = date(2026, 10, 5)


def rx(**changes):
    base = dict(id="rx1", action="start", spoken_name="Dolo six fifty", match="exact", product_id="p-dolo-650",
                candidate_ids=["p-dolo-650"], dose=Dose(amount="1", unit="tablet"), schedule=AsNeeded(type="as_needed"),
                food="after_food", duration=Duration(value=3, unit="day"), start=Start(), route=None,
                unresolved=[], quotes={})
    return ResolvedMedication(**{**base, **changes})


def test_combination_label_lists_every_component():
    assert product_label(REF.products["p-augmentin-625"]) == \
        "AUGMENTIN 625 DUO TAB (AMOXYCILLIN+CLAVULANIC ACID) 500MG+125MG"


def test_as_needed_row():
    row = medicine_row(rx(), REF, VISIT)
    assert row.label == "DOLO 650 TAB (PARACETAMOL) 650MG"
    assert row.grid == ["-", "-", "-", "-"]
    assert row.detail == "1 tablet, when needed, after food, for 3 days, start not stated"


def test_once_daily_never_gets_a_slot_and_missing_quantity_is_printed():
    row = medicine_row(rx(product_id="p-telma-40", spoken_name="Telma forty", dose=None, food=None,
                          schedule=Frequency(type="frequency", times=1, period="day"),
                          duration=Duration(value=30, unit="day")), REF, VISIT)
    assert row.grid == ["-", "-", "-", "-"]
    assert row.detail == ("Quantity not stated, once daily, time not specified, food timing not stated, "
                          "for 30 days, start not stated")
    assert "missing_quantity" in row.flags


def test_explicit_night_dose_fills_the_grid():
    row = medicine_row(rx(product_id="p-montair-lc", schedule=Grid(type="grid", m="0", a="0", e="0", n="1")), REF, VISIT)
    assert row.grid == ["0", "0", "0", "1"]


def test_ambiguous_medicine_asks_the_doctor_to_choose():
    row = medicine_row(rx(match="ambiguous", product_id=None, candidate_ids=["p-pan-40", "p-pan-d"]), REF, VISIT)
    assert row.label == ("Doctor to choose: PAN 40 TAB (PANTOPRAZOLE) 40MG or "
                         "PAN-D CAP (DOMPERIDONE+PANTOPRAZOLE) 30MG+40MG")


def test_new_prescriptions_never_appear_as_current_medicines():
    checked = CheckedExtraction(transcript_sha256="x", kept=[], dropped=[], corrections=[], issues=[],
                                medications=[rx(), rx(id="rx2", action="history", product_id="p-atorva-10")])
    assert current_medicine_lines(checked, REF) == ["Past: ATORVA TAB (ATORVASTATIN) 10MG"]


def test_header_comes_from_the_records_with_three_allergy_wordings():
    assert build_header("pat-012", "doc-001", VISIT, REF).allergy_text == "Known allergies: penicillin"
    assert build_header("pat-001", "doc-001", VISIT, REF).allergy_text == "No known allergies"
    assert build_header("pat-006", "doc-001", VISIT, REF).allergy_text == "Allergy status not recorded"


def test_taper_detail_keeps_each_steps_time_of_day():
    morning = Grid(type="grid", m="1", a="0", e="0", n="0")
    steps = [TaperStep(dose=Dose(amount=a, unit="tablet"), duration=Duration(value=3, unit="day"), when=morning)
             for a in ("2", "1")]
    row = medicine_row(rx(product_id="p-wysolone-10", dose=None, duration=None,
                          schedule=Taper(type="taper", steps=steps)), REF, VISIT)
    assert row.grid == ["-", "-", "-", "-"]
    assert row.detail == ("2 tablets in the morning for 3 days, then 1 tablet in the morning for 3 days, "
                          "after food, start not stated")
    assert "missing_quantity" not in row.flags


def test_continued_medicine_is_in_the_table_and_the_current_list():
    checked = CheckedExtraction(transcript_sha256="x", kept=[], dropped=[], corrections=[], issues=[],
                                medications=[rx(id="rx3", action="continue", product_id="p-telma-40")])
    assert [m.id for m in table_medicines(checked)] == ["rx3"]
    assert current_medicine_lines(checked, REF) == ["Continuing: TELMA 40 TAB (TELMISARTAN) 40MG"]


def test_draft_freezes_the_records_and_products_it_used(draft_report):
    assert (draft_report.version, draft_report.predecessor_hash, draft_report.resolutions) == (1, None, [])
    assert draft_report.record_snapshot["patient"] == REF.patients["pat-001"]
    assert set(draft_report.products_used) == {"p-dolo-650"}
```

Add a `draft_report` fixture to `conftest.py`. It builds a clean `DraftReport` with `assemble_draft`, with exactly this content:
- Case `fixture-1`, patient `pat-001` (Hindi), doctor `doc-001`, visit date 2026-10-05.
- Kept item `x1`: present symptom "sore throat for three days", cited by the chief complaints line "Sore throat for 3 days".
- Kept item `x2`: absent symptom "fever", cited by the history line "No fever". This exercises the absent-finding path in Task 13.
- One exact medicine, `rx1`: product `p-dolo-650`, dose 1 tablet, `AsNeeded`, after food, 3 days, start unstated.
- No issues.

- [x] **Step 2: Run the tests to make sure they fail**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_assemble.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [x] **Step 3: Implement `assemble.py` with the fixed wording above**

- [x] **Step 4: Run the tests to make sure they pass, then commit**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_assemble.py -q`
Expected: all pass

```bash
git add services/api/voicerx/pipeline/assemble.py services/api/tests
git commit -m "Assemble the draft: header, medicine table and current medicines by code"
```

---

### Task 9: Stage 2 prompt

**Files:**
- Create: `services/api/voicerx/pipeline/write_report.py`
- Test: `services/api/tests/unit/test_write_report.py`

**Interfaces:**
- Consumes: the model client's `generate` from Task 4, and `ReportFields` and `CheckedExtraction` from Task 1
- Produces: `PROMPT_VERSION = "report-v1"`, `build_report_prompt(checked: CheckedExtraction) -> tuple[str, str]`, and `write_report(client, checked) -> tuple[ReportFields, CallMeta]`

**The prompt:**
- The user text is JSON of the kept items only: `id`, `kind`, `term`, `assertion`, `certainty`, `temporality`, `laterality` and `subject`. No transcript and no medicines go in.
- The system prompt states the spec's Stage 2 rules: concise clinical English, only the given items, cite every line, keep negation and certainty ("Provisional:"), no doses, strengths or timings, and no current medicines section.
- The spec's optional per-medicine note is left out of this plan. Medicines are described by the code-built table only.

- [x] **Step 1: Write the failing test**

```python
import json

from voicerx.contracts.extraction import CheckedExtraction, ExtractedItem
from voicerx.pipeline.write_report import build_report_prompt


def test_stage_two_sees_only_checked_items_never_the_transcript():
    kept = [ExtractedItem(id="x1", kind="symptom", term="fever", quote="बुखार नहीं है", assertion="absent",
                          certainty="stated", temporality="current", laterality=None, subject="patient",
                          said_by="doctor")]
    checked = CheckedExtraction(transcript_sha256="x", kept=kept, dropped=[], medications=[], corrections=[], issues=[])
    _, user = build_report_prompt(checked)
    payload = json.loads(user.split("<<<ITEMS\n", 1)[1].split("\nITEMS>>>", 1)[0])
    assert payload == [{"id": "x1", "kind": "symptom", "term": "fever", "assertion": "absent", "certainty": "stated",
                        "temporality": "current", "laterality": None, "subject": "patient"}]
    assert "बुखार" not in user
```

- [x] **Step 2: Run the test to make sure it fails, implement, then run it to make sure it passes**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_write_report.py -q`
Expected: FAIL first, then all pass

- [x] **Step 3: Commit**

```bash
git add services/api/voicerx/pipeline/write_report.py services/api/tests/unit/test_write_report.py
git commit -m "Add stage 2 report-writing prompt"
```

---

### Task 10: Approval

**Files:**
- Create: `services/api/voicerx/approve.py`
- Test: `services/api/tests/unit/test_approve.py`

**Interfaces:**
- Consumes: `DraftReport` and `ApprovedReport` from Task 1, and `content_hash` from Task 8
- Produces: `ApprovalBlocked(Exception)`, which has the attribute `issues: list[Issue]`, `HashMismatch(Exception)`, and `approve(draft: DraftReport, by: str, at: datetime) -> ApprovedReport`
  - It recomputes `content_hash(draft)`, and raises `HashMismatch` when that differs from the stored hash.
  - The approved report keeps the draft's version and hash.

- [x] **Step 1: Write the failing tests**

```python
from datetime import datetime

import pytest

from voicerx.approve import ApprovalBlocked, HashMismatch, approve
from voicerx.contracts.issues import Issue


def test_draft_with_a_blocking_issue_cannot_be_approved(draft_report):
    blocked = draft_report.model_copy(update={"issues": [Issue(code="missing_quantity", severity="block",
                                                               target="rx1", message="no dose")]})
    with pytest.raises(ApprovalBlocked):
        approve(blocked, "Dr Test", datetime(2026, 10, 5, 12, 0))


def test_approval_needs_a_name(draft_report):
    with pytest.raises(ValueError):
        approve(draft_report, " ", datetime(2026, 10, 5, 12, 0))


def test_approved_report_keeps_the_content_and_records_who_and_when(draft_report):
    approved = approve(draft_report, "Dr Test", datetime(2026, 10, 5, 12, 0))
    assert approved.status == "approved" and approved.version == 1
    assert approved.content_hash == draft_report.content_hash
    assert approved.approved_by == "Dr Test"


def test_draft_altered_outside_the_tools_is_refused(draft_report):
    header = draft_report.header.model_copy(update={"patient_name": "Someone Else"})
    with pytest.raises(HashMismatch):
        approve(draft_report.model_copy(update={"header": header}), "Dr Test", datetime(2026, 10, 5, 12, 0))
```

The `draft_report` fixture comes from Task 8.

- [x] **Step 2: Run the tests to make sure they fail, implement, then run them to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_approve.py -q`
Expected: FAIL first, then all pass

- [x] **Step 3: Commit**

```bash
git add services/api/voicerx/approve.py services/api/tests
git commit -m "Add approval that refuses blocking issues and altered drafts"
```

---

### Task 10b: Doctor corrections

**Files:**
- Create: `services/api/voicerx/resolve.py`
- Test: `services/api/tests/unit/test_resolve.py`

**Interfaces:**
- Consumes: `DraftReport` and `Resolution` from Task 1, `medicine_issues` from Task 5, `medicine_row`, `table_medicines`, `current_medicine_lines` and `content_hash` from Task 8, and `approve` from Task 10
- Produces: `ResolutionRefused(Exception)`, and `resolve(draft: DraftReport, resolutions: list[Resolution], reference: Reference) -> DraftReport`
- **What `resolve` returns:** a new draft with `version = draft.version + 1`, `predecessor_hash = draft.content_hash`, the resolutions appended, and `checked.medications` updated.
  - Products are looked up in `draft.products_used` first, then in `reference.products`. A newly chosen product is added to `products_used`.
  - `medicine_issues` is re-run with the allergies in `record_snapshot`. The medicine rows, the current list and the content hash are rebuilt.
  - Every other issue carries over, except warnings that an `acknowledge` resolution covers.
- **The actions and their `value`:**
  - `choose_product` takes `{"product_id"}`, which must be a known product. It makes the match exact and clears `fuzzy`.
  - `set_dose` takes `{"amount", "unit"}`, `set_timing` takes `{"schedule"}` as schedule JSON, `set_food` takes `{"food"}`, and `set_duration` takes `{"value", "unit"}`. Each also clears its field from `unbound` and `unresolved`.
  - `remove_medicine` takes `{}`.
  - `confirm_order` takes `{}` and clears `speaker_unclear`.
  - `acknowledge` takes `{"code"}`, and is allowed only for a warning.
- **Refusals:** `ResolutionRefused` is raised when `by` or `reason` is blank, the target is unknown, or `acknowledge` names a blocking issue.
- **CLI:** `python -m voicerx.resolve runs/<run>/<case> --by NAME --reason TEXT`, with any of `--choose rx1=p-pan-40`, `--dose rx1=1:tablet`, `--timing rx1=<schedule JSON>`, `--food rx1=after_food`, `--duration rx1=5:day`, `--remove rx2`, `--confirm rx1` and `--ack code@target`. It renames the old draft to `draft_report.v<N>.json`, then writes the new `draft_report.json` and `report.pdf`.

Add two helpers to `conftest.py`:
- `resolved_medicine(**changes)` returns the clean Dolo medicine from the `draft_report` fixture, with those changes.
- `make_draft(medications, patient_id="pat-001")` builds a draft with `assemble_draft`, from the fixture's report fields and kept items, with these medicines and the issues that `medicine_issues` gives them.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime

import pytest

from conftest import REPO_ROOT, make_draft, resolved_medicine
from voicerx.approve import approve
from voicerx.contracts.report import Resolution
from voicerx.reference import load_reference
from voicerx.resolve import ResolutionRefused, resolve

REF = load_reference(REPO_ROOT)
AT = datetime(2026, 10, 5, 12, 0)


def fix(action, target, value, reason="checked with the patient"):
    return Resolution(id="r1", action=action, target=target, value=value, reason=reason, by="Dr Test", at=AT)


def codes(draft):
    return {i.code for i in draft.issues}


def test_choosing_a_product_clears_the_ambiguity_and_makes_a_new_version():
    draft = make_draft([resolved_medicine(match="ambiguous", product_id=None, candidate_ids=["p-pan-40", "p-pan-d"])])
    fixed = resolve(draft, [fix("choose_product", "rx1", {"product_id": "p-pan-40"})], REF)
    assert "ambiguous_product" not in codes(fixed)
    assert (fixed.version, fixed.predecessor_hash) == (2, draft.content_hash)
    assert (fixed.resolutions[0].by, fixed.resolutions[0].reason) == ("Dr Test", "checked with the patient")
    assert approve(fixed, "Dr Test", AT).version == 2


def test_setting_a_dose_clears_missing_quantity():
    draft = make_draft([resolved_medicine(dose=None)])
    fixed = resolve(draft, [fix("set_dose", "rx1", {"amount": "1", "unit": "tablet"})], REF)
    assert "missing_quantity" not in codes(fixed)


def test_confirming_the_order_clears_an_unclear_speaker():
    draft = make_draft([resolved_medicine(speaker_unclear=True)])
    assert "speaker_unclear" in codes(draft)
    assert "speaker_unclear" not in codes(resolve(draft, [fix("confirm_order", "rx1", {})], REF))


def test_blocking_issue_cannot_be_acknowledged():
    draft = make_draft([resolved_medicine(dose=None)])
    with pytest.raises(ResolutionRefused):
        resolve(draft, [fix("acknowledge", "rx1", {"code": "missing_quantity"})], REF)


def test_another_penicillin_stays_blocked_and_removing_it_clears_the_flag():
    draft = make_draft([resolved_medicine(product_id="p-augmentin-625")], patient_id="pat-012")
    swapped = resolve(draft, [fix("choose_product", "rx1", {"product_id": "p-novamox-500"})], REF)
    removed = resolve(draft, [fix("remove_medicine", "rx1", {})], REF)
    assert "allergy_conflict" in codes(swapped)
    assert "allergy_conflict" not in codes(removed) and removed.medicines == []


def test_correction_without_a_reason_is_refused():
    draft = make_draft([resolved_medicine(dose=None)])
    with pytest.raises(ResolutionRefused):
        resolve(draft, [fix("set_dose", "rx1", {"amount": "1", "unit": "tablet"}, reason=" ")], REF)
```

- [ ] **Step 2: Run the tests to make sure they fail, implement, then run them to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_resolve.py -q`
Expected: FAIL first, then all pass

- [ ] **Step 3: Commit**

```bash
git add services/api/voicerx/resolve.py services/api/tests
git commit -m "Add audited doctor corrections that make a new draft version"
```

---

### Task 11: Patient-language box

**Files:**
- Create: `services/api/voicerx/exports/patient_box.py`
- Create: `services/api/voicerx/exports/templates/lang/hi.yaml`, `te.yaml` and `ta.yaml`
- Test: `services/api/tests/unit/test_patient_box.py`

**Interfaces:**
- Consumes: `DraftReport` and `ApprovedReport`
- Produces: `PatientBox(language: str, title: str, rows: list[str], note: str, reviewed: bool)`, and `build_patient_box(report, templates_dir: Path) -> PatientBox | None`. It returns `None` when `language_pref` is `en-IN`.

**Template keys:** `title`, `official_note`, `unreviewed_note`, `ask_doctor`, `slots.{m,a,e,n}`, `food.{after_food,before_food,empty_stomach,with_food}`, `units.{tablet,capsule,puff,teaspoon}`, `frequency` (with `{n}`), `as_needed`, `as_needed_max` (with `{n}`), `duration.{day,week,month}` (with `{n}`), `row` (with `{name}`, `{dose}`, `{when}`, `{food}` and `{duration}`), `taper_row` (with `{name}`, `{steps}` and `{food}`), `taper_step` (with `{dose}`, `{when}` and `{duration}`), `then`, and `reviewed_by` (null until a native speaker signs off).

The `hi.yaml` values are fixed:
- `title`: `दवा कैसे लें`
- `official_note`: `आधिकारिक रिकॉर्ड अंग्रेज़ी रिपोर्ट है।`
- `unreviewed_note`: `अनुवाद की अभी जाँच नहीं हुई है।`
- `ask_doctor`: `डॉक्टर से पूछें`
- slots: `सुबह`, `दोपहर`, `शाम`, `रात`
- food: `खाने के बाद`, `खाने से पहले`, `खाली पेट`, `खाने के साथ`
- units: `गोली`, `कैप्सूल`, `पफ़`, `चम्मच`
- `frequency`: `दिन में {n} बार`
- `as_needed`: `ज़रूरत पड़ने पर`
- `as_needed_max`: `ज़रूरत पड़ने पर, दिन में {n} बार से ज़्यादा नहीं`
- duration: `{n} दिन`, `{n} हफ़्ते`, `{n} महीने`
- `row`: `{name}: {dose}, {when}, {food}, {duration}`
- `taper_row`: `{name}: {steps}, {food}`
- `taper_step`: `{dose} {when} {duration}`
- `then`: `, फिर `

Write the Telugu and Tamil files with the same keys. They stay `reviewed_by: null`.

**Content rules:**
- Rows cover the table medicines from `table_medicines`, in order.
- A row is written only for an exact-matched medicine, and the name is the uppercase brand.
- Any unknown value prints `ask_doctor`.
- A non-exact medicine prints `ask_doctor` in place of the whole row.

- [ ] **Step 1: Write the failing tests**

```python
from conftest import REPO_ROOT
from voicerx.contracts.medication import Dose, Duration, Grid, Taper, TaperStep
from voicerx.exports.patient_box import build_patient_box

TEMPLATES = REPO_ROOT / "services/api/voicerx/exports/templates/lang"


def test_hindi_row_comes_from_the_fixed_templates(draft_report):
    box = build_patient_box(draft_report.model_copy(update={"language_pref": "hi-IN"}), TEMPLATES)
    assert box.rows == ["DOLO 650: 1 गोली, ज़रूरत पड़ने पर, खाने के बाद, 3 दिन"]
    assert box.reviewed is False and box.note == "अनुवाद की अभी जाँच नहीं हुई है।"


def test_unknown_values_tell_the_patient_to_ask_the_doctor(draft_report):
    rx = draft_report.checked.medications[0].model_copy(update={"dose": None})
    checked = draft_report.checked.model_copy(update={"medications": [rx]})
    box = build_patient_box(draft_report.model_copy(update={"language_pref": "hi-IN", "checked": checked}), TEMPLATES)
    assert box.rows[0].startswith("DOLO 650: डॉक्टर से पूछें,")


def test_taper_row_keeps_each_steps_time_of_day(draft_report):
    morning = Grid(type="grid", m="1", a="0", e="0", n="0")
    steps = [TaperStep(dose=Dose(amount=a, unit="tablet"), duration=Duration(value=3, unit="day"), when=morning)
             for a in ("2", "1")]
    rx = draft_report.checked.medications[0].model_copy(
        update={"dose": None, "duration": None, "schedule": Taper(type="taper", steps=steps)})
    checked = draft_report.checked.model_copy(update={"medications": [rx]})
    box = build_patient_box(draft_report.model_copy(update={"language_pref": "hi-IN", "checked": checked}), TEMPLATES)
    assert box.rows == ["DOLO 650: 2 गोली सुबह 3 दिन, फिर 1 गोली सुबह 3 दिन, खाने के बाद"]


def test_english_patients_get_no_box(draft_report):
    assert build_patient_box(draft_report.model_copy(update={"language_pref": "en-IN"}), TEMPLATES) is None


def test_every_language_file_fills_every_placeholder(draft_report):
    for language in ("te-IN", "ta-IN"):
        box = build_patient_box(draft_report.model_copy(update={"language_pref": language}), TEMPLATES)
        assert box.rows and all("{" not in row for row in box.rows)
```

- [ ] **Step 2: Run the tests to make sure they fail, implement, then run them to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_patient_box.py -q`
Expected: FAIL first, then all pass

- [ ] **Step 3: Commit**

```bash
git add services/api/voicerx/exports services/api/tests/unit/test_patient_box.py
git commit -m "Add patient-language instruction box from fixed templates"
```

---

### Task 12: HTML and PDF

**Files:**
- Create: `services/api/voicerx/exports/pdf/__init__.py`, `services/api/voicerx/exports/pdf/report.html.j2` and `services/api/voicerx/exports/pdf/render.py`
- Test: `services/api/tests/unit/test_render.py`

**Interfaces:**
- Consumes: the reports from Task 1, and `PatientBox` from Task 11
- Produces:
  - `render_html(report: DraftReport | ApprovedReport, box: PatientBox | None) -> str`, using Jinja2 with autoescaping on
  - `find_browser() -> Path`, which tries `PDF_BROWSER`, then the Edge paths under Program Files (x86) and Program Files, then `/usr/bin/chromium` and `/usr/bin/google-chrome`. It raises `FileNotFoundError` if none is found.
  - `html_to_pdf(html: str, out_pdf: Path) -> Path`, which runs the browser with `--headless=new --disable-gpu --no-pdf-header-footer --user-data-dir=<temp dir> --print-to-pdf=<out>` on a temporary HTML file
- CSS fonts are `"Noto Sans", "Noto Sans Devanagari", "Noto Sans Telugu", "Noto Sans Tamil", "Nirmala UI", sans-serif`, at A4 size.
- The layout follows the spec's PDF section, in its order.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from voicerx.exports.pdf.render import find_browser, html_to_pdf, render_html


def test_draft_shows_synthetic_banner_and_draft_watermark(draft_report):
    html = render_html(draft_report, None)
    assert "SYNTHETIC DATA" in html and "DRAFT, NOT APPROVED" in html


def test_approved_report_has_no_draft_watermark(approved_report):
    assert "DRAFT, NOT APPROVED" not in render_html(approved_report, None)


def test_medicine_label_and_detail_line_are_printed(draft_report):
    html = render_html(draft_report, None)
    assert "DOLO 650 TAB (PARACETAMOL) 650MG" in html
    assert "1 tablet, when needed, after food, for 3 days, start not stated" in html


def test_empty_sections_are_listed_as_not_discussed(draft_report):
    assert "Not discussed:" in render_html(draft_report, None)


def test_approved_footer_shows_version_fingerprint_and_approver(approved_report):
    html = render_html(approved_report, None)
    assert approved_report.content_hash[:12] in html and "Dr Test" in html and "Version 1" in html


def test_record_text_is_escaped(draft_report):
    header = draft_report.header.model_copy(update={"patient_name": "<script>alert(1)</script>"})
    html = render_html(draft_report.model_copy(update={"header": header}), None)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_pdf_prints_with_the_local_browser(draft_report, tmp_path):
    try:
        find_browser()
    except FileNotFoundError:
        pytest.skip("no headless browser on this machine")
    from pypdf import PdfReader
    pdf = html_to_pdf(render_html(draft_report, None), tmp_path / "report.pdf")
    reader = PdfReader(str(pdf))
    assert len(reader.pages) >= 1 and "SYNTHETIC DATA" in reader.pages[0].extract_text()
```

Add an `approved_report` fixture to `conftest.py`: `approve(draft_report, "Dr Test", datetime(2026, 10, 5, 12, 0))`.

- [ ] **Step 2: Run the tests to make sure they fail, implement, then run them to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_render.py -q`
Expected: FAIL first, then all pass

- [ ] **Step 3: Read the rendered PDF and check the layout by eye**

Render one draft to `runs/sample/report.pdf`, then open it with the Read tool, page 1.
Expected: the banner, header, sections, a medicine table with four slot columns, the watermark and the footer are visible, and the Hindi text is shaped correctly

- [ ] **Step 4: Commit**

```bash
git add services/api/voicerx/exports/pdf services/api/tests
git commit -m "Render the report to HTML and PDF"
```

---

### Task 13: FHIR bundles

**Files:**
- Create: `services/api/voicerx/exports/fhir.py`
- Test: `services/api/tests/unit/test_fhir.py`

**Interfaces:**
- Consumes: `ApprovedReport`, and `table_medicines` from Task 8
- Produces: `build_bundles(report: ApprovedReport) -> dict[str, dict]`
  - It reads the patient, doctor, clinic and products only from the report's frozen `record_snapshot` and `products_used`, never from live reference data.
  - The keys are `"op_consult"`, and `"prescription"` only when the medicine table isn't empty.
  - It raises `ValueError` for a draft.

**Mapping:**
- Follow the spec's FHIR table.
- `fullUrl` values are `urn:uuid:` UUID5 values from `case_id` plus a resource key.
- Copy the Bundle `meta.profile`, the Composition `type` coding and the section codes from `../DATA/fhir/abdm_ig/Bundle-OPConsultNote-example-05.json` and `Bundle-Prescription-example-06.json`.
- Medicine timing:
  - Frequency becomes `timing.repeat.frequency`, with `period: 1` and `periodUnit: "d"`.
  - A grid becomes `timing.repeat.when`, using the subset of `MORN`, `AFT`, `EVE` and `NIGHT` that is filled.
  - As needed becomes `asNeededBoolean: true`.
  - A taper becomes one `dosageInstruction` per step, with `sequence` 1, 2 and so on. Each has its dose and `timing.repeat.boundsDuration`, plus `timing.repeat.when` when the step has a time.
  - `doseAndRate` appears only when the dose is known.
  - `medicationCodeableConcept.text` is the row's frozen label.

- [ ] **Step 1: Write the failing tests**

```python
import json

import pytest

from conftest import REPO_ROOT
from voicerx.exports.fhir import build_bundles

EXAMPLE = REPO_ROOT.parent / "DATA/fhir/abdm_ig/Bundle-OPConsultNote-example-05.json"


def resources(bundle, kind):
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == kind]


def test_draft_cannot_be_exported(draft_report):
    with pytest.raises(ValueError):
        build_bundles(draft_report)


def test_document_bundle_starts_with_composition_and_every_reference_resolves(approved_report):
    bundle = build_bundles(approved_report)["op_consult"]
    assert bundle["type"] == "document"
    assert bundle["entry"][0]["resource"]["resourceType"] == "Composition"
    full_urls = {e["fullUrl"] for e in bundle["entry"]}
    references = {m for m in json.dumps(bundle).split('"reference": "')[1:]}
    assert all(r.split('"')[0] in full_urls for r in references)


def test_absent_finding_is_never_a_positive_resource(approved_report):
    bundle = build_bundles(approved_report)["op_consult"]
    assert not any("fever" in json.dumps(r).lower() for r in resources(bundle, "Condition") + resources(bundle, "Observation"))


@pytest.mark.skipif(not EXAMPLE.exists(), reason="ABDM examples not downloaded")
def test_profile_and_composition_type_match_the_official_example(approved_report):
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    bundle = build_bundles(approved_report)["op_consult"]
    assert bundle["meta"]["profile"] == example["meta"]["profile"]
    assert bundle["entry"][0]["resource"]["type"] == example["entry"][0]["resource"]["type"]


def test_as_needed_medicine_has_no_invented_timing(approved_report):
    request = resources(build_bundles(approved_report)["prescription"], "MedicationRequest")[0]
    assert request["dosageInstruction"][0]["asNeededBoolean"] is True
    assert "timing" not in request["dosageInstruction"][0]


def test_medicine_text_is_the_frozen_label(approved_report):
    request = resources(build_bundles(approved_report)["prescription"], "MedicationRequest")[0]
    assert request["medicationCodeableConcept"]["text"] == approved_report.medicines[0].label
```

- [ ] **Step 2: Run the tests to make sure they fail, implement, then run them to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_fhir.py -q`
Expected: FAIL first, then all pass

- [ ] **Step 3: Commit**

```bash
git add services/api/voicerx/exports/fhir.py services/api/tests
git commit -m "Export approved reports as ABDM FHIR bundles"
```

---

### Task 14: Pipeline runner

**Files:**
- Create: `services/api/voicerx/pipeline/run.py`
- Test: `services/api/tests/unit/test_run.py`

**Interfaces:**
- Consumes: everything above
- Produces:
  - `CaseInput(case_id, family_id, encounter_index, transcript: str | None, patient_id, doctor_id, visit_date, language)`, a dataclass
  - `load_case_inputs(repo_root: Path, source: Literal["typed", "whisper"]) -> list[CaseInput]`. Typed transcripts join every utterance's text, with no speaker labels. Whisper transcripts come from `data/eval/results/whisper/<case>.txt`, and a missing file gives `transcript=None`. The list always holds all 25 cases, ordered by family and then encounter.
  - `RunResult(status: Literal["draft", "incomplete", "missing_input"], stage: str | None, error: str | None, draft: DraftReport | None, active_ids: frozenset[str] = frozenset())`. `active_ids` are the medicines active after this visit.
  - `run_case(case: CaseInput, client, reference, out_dir: Path, current_ids: frozenset[str], history_issues: tuple[Issue, ...] = ()) -> RunResult`. `history_issues` are added to the draft's issues.
  - `active_after(checked: CheckedExtraction, before: frozenset[str]) -> frozenset[str]`
  - `current_ids_for(case: CaseInput, finished: dict[str, RunResult], cases: list[CaseInput]) -> tuple[frozenset[str], list[Issue]]`
    - It chains from the previous encounter of the same family only when that encounter has a single variant, so variants a and b never chain.
    - It returns that run's `active_ids`. If that run isn't a draft, it returns no ids and a `previous_encounter_incomplete` warning.
- `run_case` first removes every file already in `out_dir`, so a failed rerun can't leave an old report looking current. A case with no transcript then writes `status.json` with `{"status": "missing_input"}` and stops.
- `run_case` writes `transcript.txt`, `extraction.json`, `checked_extraction.json`, `report_fields.json`, `draft_report.json` and `report.pdf` to `out_dir`.
- It also writes `meta.json`: the transcript SHA-256, and the model, prompt version, cache key and key index from each stage's `CallMeta`.
- When `find_browser` finds no browser, `run_case` skips `report.pdf` and records `"pdf": "no browser"` in `meta.json`. The draft still counts.
- On failure it writes `status.json` with `{"status": "incomplete", "stage": …, "error": …}` and no report.
- The approval command also writes `fhir_status.json` with `{"validation": "not officially validated"}`.
- The CLI is `python -m voicerx.pipeline.run --source typed|whisper --run-id ID [--cases ...] [--provider gemini|ollama]`. It builds the client with `build_client(Path(".env"), Path("runs/cache"), only=provider)`, records each case's provider and model in `meta.json`, runs into `runs/<run_id>/<case_id>/`, and takes each case's `current_ids` and history issues from `current_ids_for`.
- The CLI is also `python -m voicerx.approve runs/<run>/<case> --by NAME`. It writes `approved_report.json`, `report_approved.pdf`, `fhir_op_consult.json` and `fhir_prescription.json`.

- [ ] **Step 1: Write the failing tests**

```python
from dataclasses import asdict, replace

from conftest import REPO_ROOT
from voicerx.llm.client import QuotaExhausted
from voicerx.pipeline.run import RunResult, current_ids_for, load_case_inputs, run_case
from voicerx.reference import load_reference


def test_case_inputs_carry_no_expected_answers():
    cases = load_case_inputs(REPO_ROOT, "typed")
    assert len(cases) == 25
    assert set(asdict(cases[0])) == {"case_id", "family_id", "encounter_index", "transcript", "patient_id",
                                     "doctor_id", "visit_date", "language"}


def test_typed_cross_talk_case_includes_the_patient_words_without_labels():
    case = next(c for c in load_case_inputs(REPO_ROOT, "typed") if c.case_id == "fam-009-a")
    assert "मुझे चक्कर भी आते हैं" in case.transcript and "[patient]" not in case.transcript


class QuotaAtStageTwo:
    def generate(self, system, user, schema, prompt_version):
        if prompt_version.startswith("report"):
            raise QuotaExhausted("both keys used")
        from voicerx.contracts.extraction import Extraction
        from voicerx.llm.client import CallMeta
        meta = CallMeta(provider="fake", model="fake", prompt_version=prompt_version, cache_key="k", cached=False, key_index=0, attempts=1)
        return Extraction(items=[], medications=[], corrections=[]), meta


def test_quota_mid_run_is_incomplete_with_no_report(tmp_path):
    case = load_case_inputs(REPO_ROOT, "typed")[0]
    result = run_case(case, QuotaAtStageTwo(), load_reference(REPO_ROOT), tmp_path, frozenset())
    assert (result.status, result.stage) == ("incomplete", "write_report")
    assert (tmp_path / "extraction.json").exists()
    assert not (tmp_path / "draft_report.json").exists()


def test_failed_rerun_removes_the_old_report(tmp_path):
    (tmp_path / "draft_report.json").write_text("{}", encoding="utf-8")
    (tmp_path / "report.pdf").write_bytes(b"old")
    case = load_case_inputs(REPO_ROOT, "typed")[0]
    run_case(case, QuotaAtStageTwo(), load_reference(REPO_ROOT), tmp_path, frozenset())
    assert not (tmp_path / "draft_report.json").exists() and not (tmp_path / "report.pdf").exists()


def test_missing_transcript_is_reported_not_skipped(tmp_path):
    case = replace(load_case_inputs(REPO_ROOT, "typed")[0], transcript=None)
    result = run_case(case, QuotaAtStageTwo(), load_reference(REPO_ROOT), tmp_path, frozenset())
    assert result.status == "missing_input"
    assert len(load_case_inputs(REPO_ROOT, "whisper")) == 25


def test_variants_of_one_visit_never_chain():
    cases = load_case_inputs(REPO_ROOT, "typed")
    variant_b = next(c for c in cases if c.case_id == "fam-001-b")
    done = {"fam-001-a": RunResult(status="draft", stage=None, error=None, draft=None,
                                   active_ids=frozenset({"p-dolo-650"}))}
    assert current_ids_for(variant_b, done, cases) == (frozenset(), [])


def test_incomplete_earlier_visit_gives_a_warning_and_no_history():
    cases = load_case_inputs(REPO_ROOT, "typed")
    second = next(c for c in cases if c.case_id == "fam-011-v2")
    done = {"fam-011-v1": RunResult(status="incomplete", stage="extract", error="quota", draft=None)}
    ids, issues = current_ids_for(second, done, cases)
    assert ids == frozenset()
    assert [(i.code, i.severity) for i in issues] == [("previous_encounter_incomplete", "warn")]
```

- [ ] **Step 2: Run the tests to make sure they fail, implement, then run them to make sure they pass**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_run.py -q`
Expected: FAIL first, then all pass

- [ ] **Step 3: Commit**

```bash
git add services/api/voicerx/pipeline/run.py services/api/voicerx/approve.py services/api/tests/unit/test_run.py
git commit -m "Add pipeline runner and approval command"
```

---

### Task 14b: Cached end-to-end run and sabotage tests

**Files:**
- Create: `services/api/tests/fixtures/fam-001-a/extraction.json` and `report_fields.json`. These are model replies written by hand for the `fam-001-a` typed script. After the first live run, replace them with the recorded replies if those pass the clean test.
- Create: `services/api/tests/unit/test_end_to_end.py`

**Interfaces:**
- Consumes: `run_case` and `load_case_inputs` from Task 14
- Produces: `FixtureClient(directory: Path, mutate: Callable[[str, dict], dict] | None = None)` in `conftest.py`. Its `generate` loads `extraction.json` for a prompt version starting `extract`, or `report_fields.json` for one starting `report`. It applies `mutate(prompt_version, data)`, then parses the result into the requested schema. Its `CallMeta` has the provider `"fixture"`.

**The fixtures carry exactly these items and lines,** so that each sabotage finds its target. Everything is said by the doctor, and there are no corrections.

| Id | Item | Report line |
|---|---|---|
| `x1` | symptom "sore throat for three days", quote "तीन दिन से गले में दर्द" | chief complaints: "Sore throat for 3 days" |
| `x2` | symptom "dry cough", quote "सूखी खाँसी" | chief complaints: "Dry cough" |
| `x3` | absent symptom "fever", quote "बुखार नहीं है" | history: "No fever" |
| `x4` | exam "throat congested", quote "throat congested" | examination: "Throat congested" |
| `x5` | exam "tonsils normal", quote "tonsils normal" | examination: "Tonsils normal" |
| `x6` | provisional diagnosis "viral pharyngitis", quote "viral pharyngitis लग रहा है" | diagnoses: "Provisional: viral pharyngitis" |
| `x7` | advice "warm water gargles", quote "गुनगुने पानी से गरारे" | advice: "Warm water gargles" |
| `x8` | planned follow-up "come back if not better in three days", quote "तीन दिन में ठीक न हो तो दोबारा दिखाना है" | follow-up: "Review if not better in 3 days" |
| `rx1` | start "Dolo six fifty", with the phrases "एक tablet", "ज़रूरत पड़ने पर", "खाने के बाद" and "तीन दिन तक" | the medicine table |

- [ ] **Step 1: Write the fixtures and the failing tests**

```python
import pytest

from conftest import REPO_ROOT, FixtureClient
from voicerx.pipeline.run import load_case_inputs, run_case
from voicerx.reference import load_reference

REF = load_reference(REPO_ROOT)
FIXTURES = REPO_ROOT / "services/api/tests/fixtures/fam-001-a"
CASE = next(c for c in load_case_inputs(REPO_ROOT, "typed") if c.case_id == "fam-001-a")


def run(tmp_path, mutate=None):
    return run_case(CASE, FixtureClient(FIXTURES, mutate), REF, tmp_path, frozenset())


def blocking(result):
    return {i.code for i in result.draft.issues if i.severity == "block"}


def test_clean_run_gives_a_draft_with_the_right_medicine_and_no_blocks(tmp_path):
    result = run(tmp_path)
    assert result.status == "draft" and blocking(result) == set()
    row = result.draft.medicines[0]
    assert (row.label, row.detail) == ("DOLO 650 TAB (PARACETAMOL) 650MG",
                                       "1 tablet, when needed, after food, for 3 days, start not stated")
    assert (tmp_path / "draft_report.json").exists()


def edit_item(term, **changes):
    def mutate(version, data):
        if version.startswith("extract"):
            for item in data["items"]:
                if item["term"] == term:
                    item.update(changes)
        return data
    return mutate


def edit_medicine(**changes):
    def mutate(version, data):
        if version.startswith("extract"):
            data["medications"][0].update(changes)
        return data
    return mutate


def edit_line(section, text, cites=None):
    def mutate(version, data):
        if version.startswith("report"):
            data[section][0]["text"] = text
            if cites:
                data[section][0]["cites"] = cites
        return data
    return mutate


@pytest.mark.parametrize("name, mutate, code", [
    ("negation dropped from the quote", edit_item("fever", quote="बुखार"), "negation_mismatch"),
    ("negation lost in writing", edit_line("history_present_illness", "Fever"), "negation_mismatch"),
    ("dose changed", edit_medicine(dose_phrase="दो tablet"), "phrase_not_bound"),
    ("strength changed", edit_medicine(spoken_name="Dolo five hundred"), "unmatched_product"),
    ("duration borrowed from another sentence", edit_medicine(duration_phrase="तीन दिन से"), "phrase_not_bound"),
    ("relative's finding written as the patient's", edit_item("fever", subject="family"), "subject_mismatch"),
    ("provisional made definite", edit_line("diagnoses", "Viral pharyngitis"), "certainty_mismatch"),
    ("absent and present in one line",
     edit_line("chief_complaints", "Sore throat for 3 days, no fever", cites=["x1", "x3"]), "mixed_negation"),
    ("speaker unclear", edit_medicine(said_by="unclear"), "speaker_unclear"),
    ("new medicine written as current", edit_line("history_present_illness", "Already taking Dolo 650"),
     "medicine_not_in_source"),
])
def test_sabotage_is_caught(tmp_path, name, mutate, code):
    assert code in blocking(run(tmp_path, mutate)), name
```

- [ ] **Step 2: Run the tests, and fix whichever check misses a sabotage**

Run: `../.venv/Scripts/python -m pytest services/api/tests/unit/test_end_to_end.py -q`
Expected: all pass. The clean run has no blocking issue, and each sabotage is caught.

- [ ] **Step 3: Commit**

```bash
git add services/api/tests
git commit -m "Add cached end-to-end run and sabotage tests"
```

---

### Task 15: Scorer

**Files:**
- Create: `tools/eval/score_report.py`
- Test: `tools/eval/tests/test_score_report.py`, with a `conftest.py` that adds `tools/corpus` and `services/api` to `sys.path`

**Interfaces:**
- Consumes:
  - `effective` and `Family` from `tools/corpus`
  - the run files from Task 14
- Produces:
  - `match_items(expected: list[tuple[str, str]], kept: list[tuple[str, str]], typed: bool) -> list[tuple[str, str]]`, which returns pairs of expected fact id and extracted item id
  - `score_variant(...) -> dict`
  - `score_run(run_dir: Path, source: str) -> dict`, with the keys `scored` (a count), `missing_input` and `incomplete` (sorted case ids), plus the metrics below
  - a CLI that writes `data/eval/results/scores/<run_id>.json` and prints a table
- **Matching typed input:** an extracted item matches an expected fact when its quote tokens cover at least 60% of the expected evidence quote's tokens. Matching is greedy and one-to-one.
- **Matching Whisper input:** match on `rapidfuzz.fuzz.token_set_ratio(term, expected.text) >= 70`, and label the result approximate.
- **Metrics,** reported as counts out of totals:
  - facts found and missed, and false facts
  - negation and side accuracy on matched pairs
  - medicine records exactly right: product, dose, schedule, food and duration
  - expected flags raised, and unexpected blocking flags
  - cases with status `missing_input` or `incomplete`, listed by name and counted apart from the scored cases

- [ ] **Step 1: Write the failing tests**

```python
import json

from score_report import match_items, score_run


def test_typed_quotes_match_by_overlap():
    pairs = match_items(expected=[("f1", "बुखार नहीं है")], kept=[("x1", "बुखार नहीं है")], typed=True)
    assert pairs == [("f1", "x1")]


def test_weak_overlap_does_not_match():
    assert match_items(expected=[("f1", "तीन दिन से गले में दर्द")], kept=[("x1", "तीन दिन तक")], typed=True) == []


def test_one_extracted_item_cannot_match_two_facts():
    pairs = match_items(expected=[("f1", "No fever"), ("f2", "No fever")], kept=[("x1", "No fever")], typed=True)
    assert len(pairs) == 1


def test_missing_and_incomplete_cases_are_listed_not_dropped(tmp_path):
    for case, status in [("fam-001-a", "missing_input"), ("fam-001-b", "incomplete")]:
        (tmp_path / case).mkdir()
        (tmp_path / case / "status.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    scores = score_run(tmp_path, "typed")
    assert (scores["missing_input"], scores["incomplete"], scores["scored"]) == (["fam-001-a"], ["fam-001-b"], 0)
```

With typed input, both lists hold `(id, quote)` pairs. With Whisper input, they hold `(id, term)` pairs.

- [ ] **Step 2: Run the tests to make sure they fail, implement, then run them to make sure they pass**

Run: `../.venv/Scripts/python -m pytest tools/eval/tests -q`
Expected: FAIL first, then all pass

- [ ] **Step 3: Commit**

```bash
git add tools/eval
git commit -m "Add scorer that compares runs with the case families"
```

---

### Task 16: First real run

- [ ] **Step 1: Run all tests**

Run: `../.venv/Scripts/python -m pytest services/api/tests tools -q`
Expected: all pass

- [ ] **Step 2: Run the 25 typed scripts**

Run: `PYTHONPATH=services/api ../.venv/Scripts/python -m voicerx.pipeline.run --source typed --run-id typed-1`, from the repo root
Expected: each of the 25 cases ends as a draft or incomplete. On a daily limit, rerun the next day, and the cache skips work already done.

- [ ] **Step 3: Score the run**

Run: `../.venv/Scripts/python tools/eval/score_report.py runs/typed-1 --source typed`
Expected: a table, written to `data/eval/results/scores/typed-1.json`

- [ ] **Step 4: Check that the expected flags fire**

Expected:
- `missing_quantity` on `fam-004-a` and `fam-004-b`, for the continued medicine, and on `fam-005-a`
- `ambiguous_product` and `unmatched_product` on `fam-008-a`, and `unmatched_product` on `fam-008-b`
- `allergy_conflict` on `fam-012-a`

Any miss is a defect to fix before going on. Record every other blocking flag in the runbook, as a defect or as a judgement.

- [ ] **Step 5: Read two PDFs and check them by eye**

Open `runs/typed-1/fam-001-a/report.pdf` and `runs/typed-1/fam-008-a/report.pdf` with the Read tool.
Expected: the draft watermark, a correct medicine table, and the "Doctor to choose" row on `fam-008-a`

- [ ] **Step 6: Resolve and approve `fam-008-a` end to end**

Run `voicerx.resolve` on `runs/typed-1/fam-008-a` with `--by "Aditya (test)" --reason "pilot check"`. Choose `p-pan-40` for the bare Pan and remove the out-of-formulary Mucaine gel, using the medicine ids in its draft. Then run `voicerx.approve` on the same folder with `--by "Aditya (test)"`.
Expected:
- `draft_report.v1.json` is kept, and the new draft is version 2 with no blocking flag.
- The approval writes `report_approved.pdf`, `fhir_op_consult.json` and `fhir_prescription.json`.
- The approved PDF has no watermark, and its footer shows version 2.

- [ ] **Step 7: Run the Whisper transcripts and score them separately**

Run the same commands as steps 2 and 3, with `--source whisper` and the run id `whisper-1`.
Expected: 22 cases end as a draft or incomplete. `fam-011-v3`, `fam-012-a` and `fam-012-b` are `missing_input` until their audio is rendered.

- [ ] **Step 8: Run the typed scripts on the local model and compare**

Run steps 2 and 3 again with `--provider ollama` and the run id `typed-local-1`. This takes about an hour, at roughly a minute a stage.
Expected: every case ends as a draft, incomplete or `missing_input`, never a crash. Put the two score tables side by side, and count the blocking flags each model caused that the expected flags in step 4 don't explain. More such flags from the local model is expected; a wrong fact that reaches a draft without a flag is a defect in the checks, whichever model caused it.

- [ ] **Step 9: Update the runbook**

Add the results with their totals, the Gemini and local comparison, every defect found, and the decisions made. Then commit.

```bash
git add runbook.md data/eval/results/scores
git commit -m "Record first extraction and report results"
```
