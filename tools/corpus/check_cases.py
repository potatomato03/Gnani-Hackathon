"""Check case families against their scripts, seed records and the formulary.

Run from the repo root:

    python tools/corpus/check_cases.py            check everything and print coverage
    python tools/corpus/check_cases.py --write    also write the manifest and plain scripts
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from case_schema import Fact, Family, Medication

REPO_ROOT = Path(__file__).resolve().parents[2]
PUNCTUATION = ".,;:!?()\"'।॥—–-"
NUMBER_WORDS = {
    # English
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety", "hundred", "half", "once", "twice", "thrice",
    # Hindi
    "एक", "दो", "तीन", "चार", "पाँच", "पांच", "छह", "छः", "सात", "आठ", "नौ", "दस", "बारह",
    "पंद्रह", "बीस", "तीस", "चालीस", "पचास", "साठ", "सत्तर", "अस्सी", "नब्बे", "पचानवे",
    "बानवे", "अड़तालीस", "सौ", "आधा", "आधी", "डेढ़", "ढाई",
    # Telugu
    "ఒకటి", "ఒక", "రెండు", "మూడు", "నాలుగు", "ఐదు", "ఆరు", "ఏడు", "ఎనిమిది", "తొమ్మిది", "పది",
    # Tamil
    "ஒன்று", "ஒரு", "இரண்டு", "மூன்று", "நான்கு", "ஐந்து", "ஆறு", "ஏழு", "எட்டு", "ஒன்பது", "பத்து",
}
NEGATION_WORDS = {
    "no", "not", "nil", "without", "denies", "negative", "never",
    "नहीं", "नही", "न", "ना", "बिना",
    "లేదు", "లేవు", "కాదు",
    "இல்லை", "இல்லாமல்",
}
SIDE_WORDS = {
    "left": {"left", "बायां", "बाएँ", "बाएं", "बाईं", "ఎడమ", "இடது"},
    "right": {"right", "दायां", "दाएँ", "दाएं", "दाईं", "కుడి", "வலது"},
    "bilateral": {"bilateral", "both", "दोनों", "రెండు", "இரண்டு"},
}
TIME_WORDS = {
    "morning", "afternoon", "evening", "night", "bedtime",
    "सुबह", "दोपहर", "शाम", "रात",
    "ఉదయం", "మధ్యాహ్నం", "సాయంత్రం", "రాత్రి",
    "காலை", "காலையில்", "மதியம்", "மாலை", "இரவு",
}
DOCTOR_ONLY_ATTRIBUTIONS = {"clinician_exam", "clinician_statement"}
MANIFEST_FIELDS = [
    "case_id", "family_id", "patient_id", "source_parent_id",
    "split", "track", "language", "scenario_tags",
    "source_and_license", "generation_version",
    "reference_version", "annotation_version",
    "review_status", "clinical_review", "language_review",
    "voice", "noise_source", "mix_level", "audio_format",
    "audio_hash", "transcript_hash", "expected_output_hash",
]


@dataclass(frozen=True)
class Issue:
    check: str
    where: str
    detail: str

    def __str__(self):
        return f"{self.check} {self.where}: {self.detail}"


def normalise(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def tokens(text):
    stripped = (word.strip(PUNCTUATION) for word in normalise(text).split())
    return [word for word in stripped if word]


def is_number(token):
    return token in NUMBER_WORDS or any(character.isdigit() for character in token)


def has_explicit_times(quote):
    words = tokens(quote)
    if TIME_WORDS & set(words):
        return True
    run = 0
    for word in words:
        run = run + 1 if word in NUMBER_WORDS else 0
        if run >= 3:
            return True
    return False


def effective(encounter, variant):
    """Return the facts and medicines this variant expects, plus any unknown ids."""
    facts = {fact.id: fact for fact in encounter.facts}
    medications = {medication.id: medication for medication in encounter.medications}
    unknown = [item for item in [*variant.overrides, *variant.omit]
               if item not in facts and item not in medications]
    for item, changes in variant.overrides.items():
        if item in facts:
            facts[item] = Fact.model_validate({**facts[item].model_dump(), **changes})
        elif item in medications:
            medications[item] = Medication.model_validate({**medications[item].model_dump(), **changes})
    for item in variant.omit:
        facts.pop(item, None)
        medications.pop(item, None)
    return list(facts.values()), list(medications.values()), unknown


def required_evidence(facts, medications):
    keys = [fact.id for fact in facts if fact.delivery == "spoken"]
    for medication in medications:
        keys.append(f"{medication.id}.name")
        for field in ("dose", "route", "schedule", "food", "duration"):
            if getattr(medication, field) is not None:
                keys.append(f"{medication.id}.{field}")
        if medication.start.condition != "unstated":
            keys.append(f"{medication.id}.start")
        if medication.action == "stop":
            keys.append(f"{medication.id}.action")
    return keys


def base_id(key):
    return key.split(".")[0]


def mapped(utterance):
    return {base_id(item) for item in utterance.supports}


def containing(utterances, quote):
    wanted = normalise(quote)
    return [utterance for utterance in utterances if wanted in normalise(utterance.text)]


def uncovered_text(utterance, variant, keys=None):
    """Return the utterance text left over once its mapped quotes are removed."""
    text = normalise(utterance.text)
    quotes = [quote for key, quote in variant.evidence.items()
              if base_id(key) in mapped(utterance) and (keys is None or key in keys)]
    for correction in variant.corrections:
        quotes += [correction.old_quote, correction.new_quote]
    for quote in sorted((normalise(quote) for quote in quotes), key=len, reverse=True):
        text = text.replace(quote, " ")
    return text


def check_evidence(variant, facts, medications, issues):
    where = variant.variant_id
    required = required_evidence(facts, medications)
    for key in required:
        if key not in variant.evidence:
            issues.append(Issue("E-EVIDENCE-MISSING", where, f"{key} has no quote"))
    for key in variant.evidence:
        if key not in required:
            issues.append(Issue("E-EVIDENCE-UNEXPECTED", where, f"{key} is not expected to be spoken"))

    by_id = {fact.id: fact for fact in facts}
    for key, quote in variant.evidence.items():
        hits = containing(variant.utterances, quote)
        if not hits:
            issues.append(Issue("E-QUOTE-NOT-FOUND", where, f"{key}: {quote}"))
            continue
        anchored = [utterance for utterance in hits if base_id(key) in mapped(utterance)]
        if not anchored:
            issues.append(Issue("E-MAPPING", where, f"{key} is quoted from an utterance not mapped to it"))
            continue
        fact = by_id.get(key)
        doctor_only = fact is None or fact.attribution in DOCTOR_ONLY_ATTRIBUTIONS
        if doctor_only and all(utterance.speaker != "doctor" for utterance in anchored):
            issues.append(Issue("E-SPEAKER", where, f"{key} is cited from non-doctor speech"))


def check_meaning(variant, facts, medications, issues):
    where = variant.variant_id
    for fact in facts:
        quote = variant.evidence.get(fact.id)
        if fact.delivery != "spoken" or quote is None:
            continue
        words = set(tokens(quote))
        negated = bool(words & NEGATION_WORDS)
        if fact.assertion == "absent" and not negated:
            issues.append(Issue("E-NEGATION", where, f"{fact.id} is absent but its quote has no negation"))
        if fact.assertion == "present" and negated and not fact.allow_negation_cue:
            issues.append(Issue("E-NEGATION", where, f"{fact.id} is present but its quote is negated"))
        if fact.laterality and not words & SIDE_WORDS[fact.laterality]:
            issues.append(Issue("E-LATERALITY", where, f"{fact.id} should name {fact.laterality}"))
    for medication in medications:
        quote = variant.evidence.get(f"{medication.id}.schedule")
        if medication.schedule and medication.schedule.type == "grid" and quote is not None:
            if not has_explicit_times(quote):
                issues.append(Issue("E-SCHEDULE", where, f"{medication.id}: slots need an explicit time"))


def check_nothing_invented(variant, facts, medications, names, issues):
    where = variant.variant_id
    known = {fact.id for fact in facts} | {medication.id for medication in medications}
    known |= set(variant.evidence)
    name_keys = {key for key in variant.evidence if key.endswith(".name")}
    patterns = {name: re.compile(rf"(?<![^\W\d_]){re.escape(normalise(name))}(?![^\W\d_])") for name in names}

    for utterance in variant.utterances:
        unknown = [item for item in utterance.supports if item not in known]
        if unknown:
            issues.append(Issue("E-UNKNOWN-ID", where, f"{utterance.id} supports {unknown}"))
        if not utterance.supports and not utterance.filler:
            issues.append(Issue("E-UNMAPPED", where, f"{utterance.id} supports nothing"))
        if utterance.speaker != "doctor":
            continue
        for token in tokens(uncovered_text(utterance, variant)):
            if is_number(token):
                issues.append(Issue("E-NUMBER", where, f"{utterance.id} has an unaccounted number: {token}"))
        remainder = uncovered_text(utterance, variant, name_keys)
        for name, pattern in patterns.items():
            if pattern.search(remainder):
                issues.append(Issue("E-EXTRA-DRUG", where, f"{utterance.id} names {name}"))


def check_withheld(variant, facts, issues):
    where = variant.variant_id
    script = normalise(" ".join(utterance.text for utterance in variant.utterances))
    declared = {entry.id for entry in variant.withheld}
    for fact in facts:
        if fact.delivery == "unavailable" and fact.id not in declared:
            issues.append(Issue("E-WITHHELD", where, f"{fact.id} is unavailable but not withheld"))
    for entry in variant.withheld:
        for term in entry.forbidden_terms:
            if normalise(term) in script:
                issues.append(Issue("E-WITHHELD", where, f"{entry.id}: script says {term}"))


def check_corrections_and_traps(variant, facts, medications, issues):
    where = variant.variant_id
    known = {fact.id for fact in facts} | {medication.id for medication in medications}
    for correction in variant.corrections:
        if correction.target not in known:
            issues.append(Issue("E-CORRECTION", where, f"unknown target {correction.target}"))
        for quote in (correction.old_quote, correction.new_quote):
            if not containing(variant.utterances, quote):
                issues.append(Issue("E-CORRECTION", where, f"missing wording: {quote}"))
    for trap in variant.traps:
        hits = containing(variant.utterances, trap.quote)
        if not hits or any(utterance.speaker == "doctor" for utterance in hits):
            issues.append(Issue("E-TRAP", where, f"{trap.id} must be non-doctor speech"))


def check_medicines(variant, medications, formulary, issues):
    brands = {normalise(row["brand"]) for row in formulary.values()}
    for row in formulary.values():
        brands |= {normalise(alias) for alias in row["aliases"]}
    for medication in medications:
        where = f"{variant.variant_id}.{medication.id}"
        problems = []
        if medication.match == "exact":
            if medication.product_id not in formulary:
                problems.append("exact match is not in the formulary")
        elif medication.match == "ambiguous":
            if medication.product_id is not None:
                problems.append("ambiguous medicine cannot have a chosen product")
            if len(medication.candidate_ids) < 2:
                problems.append("ambiguous medicine needs two candidates")
            if not set(medication.candidate_ids) <= set(formulary):
                problems.append("candidate is not in the formulary")
        else:
            if medication.product_id or medication.candidate_ids:
                problems.append("out-of-formulary medicine cannot have candidates")
            if normalise(medication.spoken_name) in brands or any(
                normalise(medication.spoken_name).startswith(f"{brand} ") for brand in brands
            ):
                problems.append("spoken name is in the formulary")
        issues.extend(Issue("E-REF", where, problem) for problem in problems)


def chart_matches(fact, record):
    if fact.assertion == "present":
        return record["allergy_status"] == "known" and fact.text in record["allergies"]
    if fact.assertion == "absent":
        return record["allergy_status"] == "nka"
    return record["allergy_status"] == "unknown"


def check_chart(family, encounter, patients, issues):
    record = patients.get(family.patient_id)
    if record is None:
        return
    for fact in encounter.facts:
        if fact.kind == "allergy" and fact.delivery == "chart" and not chart_matches(fact, record):
            issues.append(Issue("E-CHART", encounter.encounter_id, f"{fact.id} disagrees with the seed record"))


def check_ids(family, issues):
    seen = Counter()
    for encounter in family.encounters:
        seen.update(variant.variant_id for variant in encounter.variants)
        repeated = Counter(item.id for item in [*encounter.facts, *encounter.medications])
        for item, count in repeated.items():
            if count > 1:
                issues.append(Issue("E-ID", encounter.encounter_id, f"{item} is repeated"))
    for variant_id, count in seen.items():
        if count > 1 or not variant_id.startswith(f"{family.family_id}-"):
            issues.append(Issue("E-ID", family.family_id, f"bad variant id {variant_id}"))


def check_pairs(family, issues):
    if len(family.encounters) != 1:
        return
    scripts = {normalise(" ".join(utterance.text for utterance in variant.utterances))
               for variant in family.encounters[0].variants}
    if len(scripts) < 2:
        issues.append(Issue("E-PAIR", family.family_id, "needs two variants with different scripts"))


def check_agent(family, issues):
    encounters = {encounter.encounter_id: encounter for encounter in family.encounters}
    actions = set()
    for question in family.agent_questions:
        actions.add(question.expected_action)
        where = f"{family.family_id}.{question.id}"
        encounter = encounters.get(question.encounter_id)
        if encounter is None:
            issues.append(Issue("E-AGENT", where, "unknown encounter"))
            continue
        variants = encounter.variants
        if question.variant_id is not None:
            variants = [item for item in variants if item.variant_id == question.variant_id]
            if not variants:
                issues.append(Issue("E-AGENT", where, "unknown variant"))
                continue
        if question.expected_action == "answer":
            if not question.allowed_claims:
                issues.append(Issue("E-AGENT", where, "answerable question has no allowed claims"))
            charted = {fact.id for fact in encounter.facts if fact.delivery == "chart"}
            for variant in variants:
                for claim in question.allowed_claims:
                    if claim not in variant.evidence and claim not in charted:
                        issues.append(Issue("E-AGENT", where, f"{claim} has no support in {variant.variant_id}"))
        elif not question.forbidden_claims:
            issues.append(Issue("E-AGENT", where, "needs forbidden claims"))
    if "answer" not in actions or not actions - {"answer"}:
        issues.append(Issue("E-AGENT", family.family_id, "needs one answerable and one non-answerable question"))


def check_review(family, issues):
    review = family.review
    where = family.family_id
    if review.status in {"human_reviewed", "adjudicated", "released"}:
        if not review.reviewed_by or review.reviewed_by == family.provenance.author:
            issues.append(Issue("E-REVIEW", where, f"{review.status} needs an independent reviewer"))
    if review.status == "released":
        if review.language_review != "approved" or review.clinical_review == "pending":
            issues.append(Issue("E-REVIEW", where, "released needs language and clinical review"))


def check_timeline(family, issues):
    expected = {step.after_encounter: step for step in family.timeline}
    active, stopped = set(), set()
    for encounter in family.encounters:
        for medication in encounter.medications:
            key = medication.product_id or medication.spoken_name
            if medication.action in {"start", "continue", "change"}:
                active.add(key)
                stopped.discard(key)
            elif medication.action == "stop":
                active.discard(key)
                stopped.add(key)
        step = expected.pop(encounter.encounter_id, None)
        if step and (set(step.active) != active or set(step.stopped) != stopped):
            issues.append(Issue("E-TIMELINE", encounter.encounter_id, f"replay gives active {sorted(active)}"))
    for leftover in expected:
        issues.append(Issue("E-TIMELINE", family.family_id, f"unknown encounter {leftover}"))


def check_family(raw, *, formulary, patients, doctors):
    try:
        family = Family.model_validate(raw)
    except ValidationError as error:
        return [Issue("E-SCHEMA", str(raw.get("family_id", "?")), str(error))]

    issues = []
    if family.patient_id not in patients:
        issues.append(Issue("E-REF", family.family_id, f"unknown patient {family.patient_id}"))
    names = {row["brand"] for row in formulary.values()}
    for row in formulary.values():
        names |= set(row["aliases"])

    check_ids(family, issues)
    check_pairs(family, issues)
    for encounter in family.encounters:
        if encounter.doctor_id not in doctors:
            issues.append(Issue("E-REF", encounter.encounter_id, f"unknown doctor {encounter.doctor_id}"))
        check_chart(family, encounter, patients, issues)
        for variant in encounter.variants:
            facts, medications, unknown = effective(encounter, variant)
            for item in unknown:
                issues.append(Issue("E-UNKNOWN-ID", variant.variant_id, f"override for {item}"))
            check_medicines(variant, medications, formulary, issues)
            check_evidence(variant, facts, medications, issues)
            check_meaning(variant, facts, medications, issues)
            check_nothing_invented(variant, facts, medications, names, issues)
            check_withheld(variant, facts, issues)
            check_corrections_and_traps(variant, facts, medications, issues)
    check_agent(family, issues)
    check_review(family, issues)
    check_timeline(family, issues)
    return issues


def check_seed(patients):
    issues = []
    seen = set()
    for record in patients:
        where = record.get("patient_id", "?")
        if where in seen:
            issues.append(Issue("E-SEED", where, "duplicate patient id"))
        seen.add(where)
        if record.get("synthetic") is not True:
            issues.append(Issue("E-SEED", where, "not marked synthetic"))
        if not re.fullmatch(r"\+91-00000-\d{5}", record.get("phone", "")):
            issues.append(Issue("E-SEED", where, "phone could belong to a real person"))
        if (record.get("allergy_status") == "known") != bool(record.get("allergies")):
            issues.append(Issue("E-SEED", where, "allergy status and list disagree"))
    return issues


def check_splits(families, splits):
    issues = []
    assigned = splits["families"]
    ids = {family["family_id"] for family in families}
    for family_id in ids - set(assigned):
        issues.append(Issue("E-SPLIT", family_id, "has no split"))
    for family_id, split in assigned.items():
        if family_id not in ids:
            issues.append(Issue("E-SPLIT", family_id, "is not a known family"))
        if split not in {"dev", "held_out"}:
            issues.append(Issue("E-SPLIT", family_id, f"unknown split {split}"))
    patient_splits = {}
    for family in families:
        if family["family_id"] in assigned:
            patient_splits.setdefault(family["patient_id"], set()).add(assigned[family["family_id"]])
    for patient_id, used in patient_splits.items():
        if len(used) > 1:
            issues.append(Issue("E-SPLIT", patient_id, f"crosses splits: {sorted(used)}"))
    return issues


def coverage(families):
    parsed = [Family.model_validate(raw) for raw in families]
    summary = {
        "families": len(parsed),
        "variants": sum(len(encounter.variants) for family in parsed for encounter in family.encounters),
    }
    for field in ("language", "capture_mode", "specialty", "track"):
        summary[field] = dict(Counter(getattr(family, field) for family in parsed))
    summary["scenario_tags"] = dict(Counter(tag for family in parsed for tag in family.scenario_tags))
    return summary


def script_lines(variant):
    return [f"[{utterance.speaker}] {utterance.text}" for utterance in variant.utterances]


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest_rows(families, splits, audio=None):
    audio = audio or {}
    rows = []
    for raw in families:
        family = Family.model_validate(raw)
        for encounter in family.encounters:
            for variant in encounter.variants:
                facts, medications, _ = effective(encounter, variant)
                expected = json.dumps(
                    {
                        "facts": [fact.model_dump(mode="json") for fact in facts],
                        "medications": [medication.model_dump(mode="json") for medication in medications],
                        "corrections": [item.model_dump(mode="json") for item in variant.corrections],
                        "expected_flags": variant.expected_flags,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                row = dict.fromkeys(MANIFEST_FIELDS, "")
                row.update(
                    case_id=variant.variant_id,
                    family_id=family.family_id,
                    patient_id=family.patient_id,
                    source_parent_id=family.provenance.source_parent_id or "",
                    split=splits["families"].get(family.family_id, ""),
                    track=family.track,
                    language=family.language,
                    scenario_tags=";".join(family.scenario_tags),
                    source_and_license=family.provenance.source_and_license,
                    generation_version=family.provenance.generation_version,
                    reference_version=family.provenance.reference_version,
                    annotation_version=family.provenance.annotation_version,
                    review_status=family.review.status,
                    clinical_review=family.review.clinical_review,
                    language_review=family.review.language_review,
                    transcript_hash=sha256("\n".join(script_lines(variant))),
                    expected_output_hash=sha256(expected),
                )
                clip = audio.get(variant.variant_id)
                if clip:
                    row.update(
                        voice=f"{clip['source']}:{clip['voice']}",
                        audio_format=clip["audio_format"],
                        audio_hash=clip["audio_hash"],
                    )
                rows.append(row)
    return rows


def load_formulary(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            row["id"]: {"brand": row["brand"], "aliases": [item for item in row["aliases"].split(";") if item]}
            for row in csv.DictReader(handle)
        }


def load_repo(root):
    data = root / "data"
    families = [yaml.safe_load(path.read_text(encoding="utf-8"))
                for path in sorted((data / "eval" / "cases").glob("*.yaml"))]
    patients = json.loads((data / "seed" / "patients.json").read_text(encoding="utf-8"))
    doctors = json.loads((data / "seed" / "doctors.json").read_text(encoding="utf-8"))
    formulary = load_formulary(data / "formulary" / "products.csv")
    splits = json.loads((data / "eval" / "splits.json").read_text(encoding="utf-8"))
    return families, patients, doctors, formulary, splits


def check_repo(root=REPO_ROOT):
    try:
        families, patients, doctors, formulary, splits = load_repo(root)
    except OSError as error:
        return [Issue("E-REPO", str(root), str(error))]
    if not families:
        return [Issue("E-REPO", str(root), "no case files found")]
    issues = check_seed(patients)
    patient_records = {record["patient_id"]: record for record in patients}
    doctor_ids = {record["doctor_id"] for record in doctors}
    for family in families:
        issues += check_family(family, formulary=formulary, patients=patient_records, doctors=doctor_ids)
    issues += check_splits(families, splits)
    return issues


def load_audio_index(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["case_id"]: row for row in csv.DictReader(handle)}


def write_outputs(root, families, splits):
    data = root / "data" / "eval"
    audio = load_audio_index(data / "audio_index.csv")
    with (data / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest_rows(families, splits, audio))
    for raw in families:
        for encounter in Family.model_validate(raw).encounters:
            for variant in encounter.variants:
                path = data / "scripts" / f"{variant.variant_id}.txt"
                path.write_text("\n".join(script_lines(variant)) + "\n", encoding="utf-8", newline="\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the manifest and plain scripts")
    options = parser.parse_args()

    issues = check_repo()
    for issue in issues:
        print(issue)
    if issues:
        print(f"{len(issues)} issue(s) found")
        return 1
    families, _, _, _, splits = load_repo(REPO_ROOT)
    print(json.dumps(coverage(families), ensure_ascii=False, indent=2))
    if options.write:
        write_outputs(REPO_ROOT, families, splits)
        print("wrote data/eval/manifest.csv and data/eval/scripts/")
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
