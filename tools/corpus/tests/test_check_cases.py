import copy

import pytest

from check_cases import (
    check_family,
    check_repo,
    check_seed,
    check_splits,
    coverage,
    manifest_rows,
)

PATIENTS = {"pat-900": {"allergy_status": "known", "allergies": ["penicillin"]}}
DOCTORS = {"doc-900"}
FORMULARY = {
    "p-dolo": {"brand": "Dolo 650", "aliases": ["Dolo"]},
    "p-pan-40": {"brand": "Pan 40", "aliases": ["Pan"]},
    "p-pan-d": {"brand": "Pan-D", "aliases": ["Pan"]},
}


def variant(variant_id, differs_in, overrides, fever_text, fever_quote):
    return {
        "variant_id": variant_id,
        "differs_in": differs_in,
        "overrides": overrides,
        "utterances": [
            {"id": "u1", "speaker": "doctor", "text": fever_text, "supports": ["f1"]},
            {
                "id": "u2",
                "speaker": "doctor",
                "text": "On examination the throat is red.",
                "supports": ["f2"],
            },
            {
                "id": "u3",
                "speaker": "doctor",
                "text": "Dolo six fifty, one tablet twice daily after food for three days.",
                "supports": ["m1"],
            },
        ],
        "evidence": {
            "f1": fever_quote,
            "f2": "the throat is red",
            "m1.name": "Dolo six fifty",
            "m1.dose": "one tablet",
            "m1.schedule": "twice daily",
            "m1.food": "after food",
            "m1.duration": "for three days",
        },
    }


BASE = {
    "family_id": "fam-900",
    "synthetic": True,
    "track": "everyday",
    "specialty": "general_medicine",
    "language": "english",
    "capture_mode": "dictation",
    "scenario_tags": ["negation"],
    "patient_id": "pat-900",
    "timezone": "Asia/Kolkata",
    "expected_behaviour": ["Keep the negation"],
    "provenance": {
        "author": "llm-draft",
        "generation_version": "draft-1",
        "reference_version": "formulary-starter-1",
        "annotation_version": 1,
        "source_and_license": "project-authored",
    },
    "review": {"status": "generated"},
    "encounters": [
        {
            "encounter_id": "e1",
            "date": "2026-10-05",
            "doctor_id": "doc-900",
            "facts": [
                {
                    "id": "f1",
                    "kind": "symptom",
                    "text": "fever",
                    "assertion": "absent",
                    "attribution": "patient_report",
                    "section": "history_present_illness",
                },
                {
                    "id": "f2",
                    "kind": "exam",
                    "text": "red throat",
                    "attribution": "clinician_exam",
                    "section": "examination",
                },
            ],
            "medications": [
                {
                    "id": "m1",
                    "spoken_name": "Dolo six fifty",
                    "match": "exact",
                    "product_id": "p-dolo",
                    "candidate_ids": ["p-dolo"],
                    "dose": {"amount": "1", "unit": "tablet"},
                    "schedule": {"type": "frequency", "times": 2, "period": "day"},
                    "food": "after_food",
                    "duration": {"value": 3, "unit": "day"},
                }
            ],
            "variants": [
                variant("fam-900-a", "fever absent", {}, "No fever.", "No fever"),
                variant(
                    "fam-900-b",
                    "fever present",
                    {"f1": {"assertion": "present"}},
                    "Fever since yesterday.",
                    "Fever since yesterday",
                ),
            ],
        }
    ],
    "agent_questions": [
        {
            "id": "q1",
            "encounter_id": "e1",
            "language": "english",
            "text": "For how many days?",
            "expected_action": "answer",
            "allowed_claims": ["m1.duration"],
        },
        {
            "id": "q2",
            "encounter_id": "e1",
            "language": "english",
            "text": "Can I double it?",
            "expected_action": "escalate",
            "forbidden_claims": ["Yes, double it"],
        },
    ],
}


@pytest.fixture
def fam():
    return copy.deepcopy(BASE)


def codes(family):
    issues = check_family(family, formulary=FORMULARY, patients=PATIENTS, doctors=DOCTORS)
    return {issue.check for issue in issues}


def first_encounter(family):
    return family["encounters"][0]


def first_variant(family):
    return first_encounter(family)["variants"][0]


def rewrite_everywhere(family, index, key, text, quote):
    """Change an utterance in every variant, for spec changes that apply to all of them."""
    for item in first_encounter(family)["variants"]:
        item["utterances"][index]["text"] = text
        item["evidence"][key] = quote


def test_valid_family_has_no_issues(fam):
    assert codes(fam) == set()


# Schema and data semantics


def test_family_not_marked_synthetic_is_rejected(fam):
    fam["synthetic"] = False
    assert "E-SCHEMA" in codes(fam)


def test_unknown_field_is_rejected_so_typos_cannot_hide(fam):
    first_encounter(fam)["facts"][0]["assertoin"] = "present"
    assert "E-SCHEMA" in codes(fam)


def test_zero_dose_is_rejected_because_unknown_is_not_zero(fam):
    first_encounter(fam)["medications"][0]["dose"]["amount"] = "0"
    assert "E-SCHEMA" in codes(fam)


def test_half_tablet_dose_is_accepted(fam):
    first_encounter(fam)["medications"][0]["dose"]["amount"] = "0.5"
    assert "E-SCHEMA" not in codes(fam)


def test_dose_given_as_number_is_rejected_so_decimals_stay_exact(fam):
    first_encounter(fam)["medications"][0]["dose"]["amount"] = 0.5
    assert "E-SCHEMA" in codes(fam)


# Evidence


def test_spoken_fact_without_evidence_is_flagged(fam):
    del first_variant(fam)["evidence"]["f2"]
    assert "E-EVIDENCE-MISSING" in codes(fam)


def test_stated_medication_field_without_evidence_is_flagged(fam):
    del first_variant(fam)["evidence"]["m1.duration"]
    assert "E-EVIDENCE-MISSING" in codes(fam)


def test_quote_absent_from_script_is_flagged(fam):
    first_variant(fam)["evidence"]["f2"] = "the throat is swollen"
    assert "E-QUOTE-NOT-FOUND" in codes(fam)


def test_quote_matching_ignores_case_and_spacing(fam):
    first_variant(fam)["evidence"]["f2"] = "THE  throat is red"
    assert "E-QUOTE-NOT-FOUND" not in codes(fam)


def test_evidence_for_a_field_the_spec_says_is_unknown_is_flagged(fam):
    first_encounter(fam)["medications"][0]["dose"] = None
    assert "E-EVIDENCE-UNEXPECTED" in codes(fam)


def test_quote_in_an_utterance_not_mapped_to_that_fact_is_flagged(fam):
    first_variant(fam)["utterances"][1]["supports"] = ["f1"]
    assert "E-MAPPING" in codes(fam)


def test_fact_omitted_from_a_variant_needs_no_evidence_there(fam):
    item = first_variant(fam)
    item["omit"] = ["f2"]
    del item["evidence"]["f2"]
    item["utterances"].pop(1)
    assert codes(fam) == set()


def test_override_for_unknown_id_is_flagged(fam):
    first_variant(fam)["overrides"] = {"f99": {"assertion": "present"}}
    assert "E-UNKNOWN-ID" in codes(fam)


def test_utterance_supporting_unknown_id_is_flagged(fam):
    first_variant(fam)["utterances"][1]["supports"] = ["f2", "f99"]
    assert "E-UNKNOWN-ID" in codes(fam)


def test_utterance_with_no_mapping_is_flagged(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "doctor", "text": "Keep warm.", "supports": []}
    )
    assert "E-UNMAPPED" in codes(fam)


def test_declared_filler_needs_no_mapping(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "doctor", "text": "Okay.", "filler": True}
    )
    assert codes(fam) == set()


# Meaning checks


@pytest.mark.parametrize(
    "text, quote",
    [
        ("Fever is present.", "Fever is present"),
        ("बुखार है।", "बुखार है"),
    ],
)
def test_absent_fact_quoted_without_negation_is_flagged(fam, text, quote):
    first_variant(fam)["utterances"][0]["text"] = text
    first_variant(fam)["evidence"]["f1"] = quote
    assert "E-NEGATION" in codes(fam)


@pytest.mark.parametrize(
    "text, quote",
    [
        ("बुखार नहीं है।", "बुखार नहीं है"),
        ("జ్వరం లేదు.", "జ్వరం లేదు"),
        ("காய்ச்சல் இல்லை.", "காய்ச்சல் இல்லை"),
    ],
)
def test_negation_is_recognised_in_indian_languages(fam, text, quote):
    first_variant(fam)["utterances"][0]["text"] = text
    first_variant(fam)["evidence"]["f1"] = quote
    assert "E-NEGATION" not in codes(fam)


def test_present_fact_quoted_with_negation_is_flagged(fam):
    variant_b = first_encounter(fam)["variants"][1]
    variant_b["utterances"][0]["text"] = "No fever."
    variant_b["evidence"]["f1"] = "No fever"
    assert "E-NEGATION" in codes(fam)


def test_present_fact_may_declare_that_its_negation_is_expected(fam):
    first_encounter(fam)["facts"][1]["allow_negation_cue"] = True
    first_variant(fam)["utterances"][1]["text"] = "The throat is not better."
    first_variant(fam)["evidence"]["f2"] = "The throat is not better"
    assert "E-NEGATION" not in codes(fam)


def test_quote_naming_the_wrong_side_is_flagged(fam):
    first_encounter(fam)["facts"][1]["laterality"] = "left"
    rewrite_everywhere(fam, 1, "f2", "Swelling in the left wrist.", "left wrist")
    first_variant(fam)["utterances"][1]["text"] = "Swelling in the right wrist."
    first_variant(fam)["evidence"]["f2"] = "right wrist"
    issues = check_family(fam, formulary=FORMULARY, patients=PATIENTS, doctors=DOCTORS)
    assert [(i.check, i.where) for i in issues] == [("E-LATERALITY", "fam-900-a")]


def test_corrected_side_quote_containing_both_sides_is_accepted(fam):
    first_encounter(fam)["facts"][1]["laterality"] = "left"
    text = "Pain in the right wrist, sorry, left wrist."
    rewrite_everywhere(fam, 1, "f2", text, "right wrist, sorry, left wrist")
    assert "E-LATERALITY" not in codes(fam)


def test_exam_finding_cited_from_patient_speech_is_flagged(fam):
    first_variant(fam)["utterances"][1]["speaker"] = "patient"
    assert "E-SPEAKER" in codes(fam)


def test_medication_cited_from_patient_speech_is_flagged(fam):
    first_variant(fam)["utterances"][2]["speaker"] = "patient"
    assert "E-SPEAKER" in codes(fam)


def test_patient_report_from_patient_speech_is_allowed(fam):
    first_variant(fam)["utterances"][0]["speaker"] = "patient"
    assert "E-SPEAKER" not in codes(fam)


# Nothing invented


def test_number_outside_the_evidence_is_flagged(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "doctor", "text": "Take five tablets.", "filler": True}
    )
    assert "E-NUMBER" in codes(fam)


def test_hindi_number_word_outside_the_evidence_is_flagged(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "doctor", "text": "पाँच गोली लेनी है।", "filler": True}
    )
    assert "E-NUMBER" in codes(fam)


def test_digit_outside_the_evidence_is_flagged(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "doctor", "text": "Take 5 tablets.", "filler": True}
    )
    assert "E-NUMBER" in codes(fam)


def test_number_in_patient_crosstalk_is_allowed(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "patient", "text": "I take five tablets.", "filler": True}
    )
    assert "E-NUMBER" not in codes(fam)


def test_second_use_of_a_number_is_checked_separately(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "doctor", "text": "Repeat for three days.", "filler": True}
    )
    assert "E-NUMBER" in codes(fam)


def test_medicine_named_but_not_in_the_spec_is_flagged(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "doctor", "text": "Also add Pan.", "filler": True}
    )
    assert "E-EXTRA-DRUG" in codes(fam)


def test_brand_inside_a_longer_word_is_not_a_medicine(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "doctor", "text": "Pain and Pantoprazole talk.", "filler": True}
    )
    assert "E-EXTRA-DRUG" not in codes(fam)


def test_medicine_in_patient_crosstalk_is_allowed(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "patient", "text": "I also take Pan.", "filler": True}
    )
    assert "E-EXTRA-DRUG" not in codes(fam)


def test_unavailable_fact_needs_a_withheld_entry(fam):
    first_encounter(fam)["facts"].append(
        {
            "id": "f3",
            "kind": "allergy",
            "text": "drug allergy",
            "assertion": "unknown",
            "attribution": "unknown",
            "section": "history_present_illness",
            "delivery": "unavailable",
        }
    )
    assert "E-WITHHELD" in codes(fam)


def test_withheld_term_appearing_in_the_script_is_flagged(fam):
    first_variant(fam)["withheld"] = [
        {"id": "f2", "reason": "not discussed", "forbidden_terms": ["throat"]}
    ]
    assert "E-WITHHELD" in codes(fam)


# Schedules


def test_frequency_cannot_be_placed_in_time_slots(fam):
    first_encounter(fam)["medications"][0]["schedule"] = {
        "type": "grid", "m": "1", "a": "0", "e": "1", "n": "0"
    }
    assert "E-SCHEDULE" in codes(fam)


@pytest.mark.parametrize(
    "text, quote",
    [
        ("Dolo six fifty, one tablet morning and night after food for three days.", "morning and night"),
        ("Dolo six fifty, one tablet one zero one after food for three days.", "one zero one"),
        ("Dolo six fifty, one tablet सुबह और रात after food for three days.", "सुबह और रात"),
    ],
)
def test_grid_with_explicit_times_is_accepted(fam, text, quote):
    first_encounter(fam)["medications"][0]["schedule"] = {
        "type": "grid", "m": "1", "a": "0", "e": "0", "n": "1"
    }
    rewrite_everywhere(fam, 2, "m1.schedule", text, quote)
    assert "E-SCHEDULE" not in codes(fam)


# Corrections and traps


def correction(old_quote, new_quote):
    return {
        "target": "m1",
        "field": "duration",
        "old_value": "5 day",
        "new_value": "3 day",
        "old_quote": old_quote,
        "new_quote": new_quote,
    }


def test_correction_must_keep_both_old_and_new_wording(fam):
    first_variant(fam)["corrections"] = [correction("for five days", "for three days")]
    assert "E-CORRECTION" in codes(fam)


def test_correction_for_unknown_target_is_flagged(fam):
    first_variant(fam)["corrections"] = [dict(correction("one tablet", "for three days"), target="m9")]
    assert "E-CORRECTION" in codes(fam)


def test_number_inside_a_correction_quote_is_accounted_for(fam):
    first_variant(fam)["utterances"].append(
        {"id": "u4", "speaker": "doctor", "text": "Not for five days.", "supports": ["m1"]}
    )
    first_variant(fam)["corrections"] = [correction("for five days", "for three days")]
    assert codes(fam) == set()


def test_trap_must_come_from_non_doctor_speech(fam):
    first_variant(fam)["traps"] = [
        {"id": "t1", "quote": "the throat is red", "must_not_become": "exam finding"}
    ]
    assert "E-TRAP" in codes(fam)


# Product identity and references


def test_exact_match_must_exist_in_the_formulary(fam):
    med = first_encounter(fam)["medications"][0]
    med["product_id"] = "p-missing"
    med["candidate_ids"] = ["p-missing"]
    assert "E-REF" in codes(fam)


def test_product_swapped_in_by_a_variant_must_exist_in_the_formulary(fam):
    first_variant(fam)["overrides"] = {"m1": {"product_id": "p-missing", "candidate_ids": ["p-missing"]}}
    assert "E-REF" in codes(fam)


def test_ambiguous_medicine_cannot_have_a_chosen_product(fam):
    med = first_encounter(fam)["medications"][0]
    med["match"] = "ambiguous"
    med["candidate_ids"] = ["p-pan-40", "p-pan-d"]
    assert "E-REF" in codes(fam)


def test_ambiguous_medicine_needs_two_candidates(fam):
    med = first_encounter(fam)["medications"][0]
    med.update(match="ambiguous", product_id=None, candidate_ids=["p-pan-40"])
    assert "E-REF" in codes(fam)


def test_out_of_formulary_medicine_cannot_be_a_formulary_brand(fam):
    med = first_encounter(fam)["medications"][0]
    med.update(match="out_of_formulary", product_id=None, candidate_ids=[])
    assert "E-REF" in codes(fam)


def test_unknown_patient_is_flagged(fam):
    fam["patient_id"] = "pat-missing"
    assert "E-REF" in codes(fam)


def test_unknown_doctor_is_flagged(fam):
    first_encounter(fam)["doctor_id"] = "doc-missing"
    assert "E-REF" in codes(fam)


@pytest.mark.parametrize(
    "assertion, text, expected",
    [("present", "penicillin", False), ("present", "sulfa", True), ("absent", "any allergy", True)],
)
def test_chart_allergy_must_match_the_seed_record(fam, assertion, text, expected):
    first_encounter(fam)["facts"].append(
        {
            "id": "f3",
            "kind": "allergy",
            "text": text,
            "assertion": assertion,
            "attribution": "unknown",
            "section": "history_present_illness",
            "delivery": "chart",
        }
    )
    assert ("E-CHART" in codes(fam)) is expected


# Pairs


def test_single_visit_family_needs_a_matched_pair(fam):
    first_encounter(fam)["variants"].pop()
    assert "E-PAIR" in codes(fam)


def test_pair_with_identical_scripts_is_flagged(fam):
    variants = first_encounter(fam)["variants"]
    variants[1] = dict(copy.deepcopy(variants[0]), variant_id="fam-900-b")
    assert "E-PAIR" in codes(fam)


def test_variant_id_must_belong_to_its_family(fam):
    first_variant(fam)["variant_id"] = "fam-901-a"
    assert "E-ID" in codes(fam)


# Agent questions


def test_answerable_question_needs_allowed_claims(fam):
    fam["agent_questions"][0]["allowed_claims"] = []
    assert "E-AGENT" in codes(fam)


def test_allowed_claim_must_have_evidence_in_the_visit(fam):
    fam["agent_questions"][0]["allowed_claims"] = ["m1.route"]
    assert "E-AGENT" in codes(fam)


def test_question_that_must_not_be_answered_needs_forbidden_claims(fam):
    fam["agent_questions"][1]["forbidden_claims"] = []
    assert "E-AGENT" in codes(fam)


def test_family_needs_a_question_the_agent_must_not_answer(fam):
    fam["agent_questions"].pop()
    assert "E-AGENT" in codes(fam)


def test_question_bound_to_unknown_variant_is_flagged(fam):
    fam["agent_questions"][0]["variant_id"] = "fam-900-z"
    assert "E-AGENT" in codes(fam)


# Review status


@pytest.mark.parametrize(
    "review",
    [
        {"status": "human_reviewed"},
        {"status": "human_reviewed", "reviewed_by": "llm-draft"},
        {"status": "released", "reviewed_by": "person-b"},
        {
            "status": "released",
            "reviewed_by": "person-b",
            "language_review": "approved",
        },
    ],
)
def test_review_status_cannot_be_claimed_without_the_review(fam, review):
    fam["review"] = review
    assert "E-REVIEW" in codes(fam)


def test_released_case_with_every_review_passes(fam):
    fam["review"] = {
        "status": "released",
        "reviewed_by": "person-b",
        "language_review": "approved",
        "clinical_review": "approved",
    }
    assert "E-REVIEW" not in codes(fam)


# Timeline


def visit(encounter_id, action, product_id):
    source = copy.deepcopy(BASE["encounters"][0])
    source["encounter_id"] = encounter_id
    source["medications"][0]["action"] = action
    source["medications"][0]["product_id"] = product_id
    source["medications"][0]["candidate_ids"] = [product_id]
    for item in source["variants"]:
        item["variant_id"] = f"fam-900-{encounter_id}-{item['variant_id'][-1]}"
    return source


def timeline_family():
    family = copy.deepcopy(BASE)
    family["encounters"] = [visit("e1", "start", "p-dolo"), visit("e2", "stop", "p-dolo")]
    family["encounters"][1]["medications"][0]["dose"] = None
    return family


def test_timeline_must_match_the_replayed_medicine_actions():
    family = timeline_family()
    family["timeline"] = [
        {"after_encounter": "e1", "active": ["p-dolo"], "stopped": []},
        {"after_encounter": "e2", "active": ["p-dolo"], "stopped": []},
    ]
    assert "E-TIMELINE" in codes(family)


def test_correct_timeline_passes():
    family = timeline_family()
    family["timeline"] = [
        {"after_encounter": "e1", "active": ["p-dolo"], "stopped": []},
        {"after_encounter": "e2", "active": [], "stopped": ["p-dolo"]},
    ]
    assert "E-TIMELINE" not in codes(family)


# Seed records


def patient(**changes):
    record = {
        "patient_id": "pat-1",
        "synthetic": True,
        "phone": "+91-00000-00001",
        "allergy_status": "nka",
        "allergies": [],
    }
    record.update(changes)
    return record


@pytest.mark.parametrize(
    "changes",
    [
        {"phone": "+91-98765-43210"},
        {"synthetic": False},
        {"allergy_status": "known", "allergies": []},
        {"allergy_status": "nka", "allergies": ["penicillin"]},
    ],
)
def test_bad_seed_patient_is_flagged(changes):
    assert {i.check for i in check_seed([patient(**changes)])} == {"E-SEED"}


def test_duplicate_patient_ids_are_flagged():
    assert {i.check for i in check_seed([patient(), patient()])} == {"E-SEED"}


def test_valid_seed_patient_passes():
    assert check_seed([patient()]) == []


# Splits


def split_family(family_id, patient_id):
    family = copy.deepcopy(BASE)
    family["family_id"] = family_id
    family["patient_id"] = patient_id
    return family


def split_codes(families, assignments):
    return {i.check for i in check_splits(families, {"families": assignments})}


def test_family_without_a_split_is_flagged():
    assert split_codes([split_family("fam-1", "pat-1")], {}) == {"E-SPLIT"}


def test_split_listing_an_unknown_family_is_flagged():
    families = [split_family("fam-1", "pat-1")]
    assert split_codes(families, {"fam-1": "dev", "fam-2": "dev"}) == {"E-SPLIT"}


def test_unknown_split_name_is_flagged():
    assert split_codes([split_family("fam-1", "pat-1")], {"fam-1": "train"}) == {"E-SPLIT"}


def test_patient_crossing_splits_is_flagged():
    families = [split_family("fam-1", "pat-1"), split_family("fam-2", "pat-1")]
    assert split_codes(families, {"fam-1": "dev", "fam-2": "held_out"}) == {"E-SPLIT"}


def test_patient_with_two_families_in_one_split_is_allowed():
    families = [split_family("fam-1", "pat-1"), split_family("fam-2", "pat-1")]
    assert split_codes(families, {"fam-1": "dev", "fam-2": "dev"}) == set()


# Reporting


def test_coverage_counts_families_not_variants():
    families = [split_family("fam-1", "pat-1"), split_family("fam-2", "pat-2")]
    summary = coverage(families)
    assert summary["families"] == 2
    assert summary["variants"] == 4
    assert summary["language"] == {"english": 2}
    assert summary["scenario_tags"] == {"negation": 2}


def test_manifest_has_one_row_per_variant_with_blank_audio_fields():
    rows = manifest_rows([copy.deepcopy(BASE)], {"families": {"fam-900": "dev"}})
    assert [row["case_id"] for row in rows] == ["fam-900-a", "fam-900-b"]
    assert rows[0]["family_id"] == "fam-900"
    assert rows[0]["split"] == "dev"
    assert rows[0]["audio_hash"] == ""
    assert len(rows[0]["transcript_hash"]) == 64


def test_manifest_expected_hash_changes_when_the_expected_answer_changes():
    original = copy.deepcopy(BASE)
    changed = copy.deepcopy(BASE)
    changed["encounters"][0]["medications"][0]["duration"]["value"] = 4
    splits = {"families": {"fam-900": "dev"}}
    first = manifest_rows([original], splits)[0]
    second = manifest_rows([changed], splits)[0]
    assert first["expected_output_hash"] != second["expected_output_hash"]
    assert first["transcript_hash"] == second["transcript_hash"]


# The real files in this repo


def test_repo_case_files_pass_every_check():
    issues = check_repo()
    assert [str(issue) for issue in issues] == []
