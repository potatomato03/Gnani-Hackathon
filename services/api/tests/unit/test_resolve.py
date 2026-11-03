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


def flagged_draft():
    # A Check 1 block on item x2 and a Check 2 block on the line that cites it (runbook D-87).
    from voicerx.contracts.issues import Issue
    from voicerx.contracts.report import ReportLine
    from voicerx.pipeline.assemble import content_hash

    draft = make_draft([resolved_medicine()])
    draft.sections["history_present_illness"].append(ReportLine(text="Dry cough", cites=["x1"]))
    draft.issues += [Issue(code="negation_mismatch", severity="block", target="x2", message="negation mismatch"),
                     Issue(code="negation_mismatch", severity="block", target="history_present_illness:0",
                           message="negation mismatch"),
                     Issue(code="section_mismatch", severity="warn", target="history_present_illness:1",
                           message="section mismatch")]
    draft.content_hash = content_hash(draft)
    return draft


def test_editing_a_flagged_line_clears_its_flags_and_keeps_its_citations():
    draft = flagged_draft()
    fixed = resolve(draft, [fix("edit_line", "history_present_illness:0", {"text": "No fever since yesterday"})], REF)
    assert fixed.sections["history_present_illness"][0].text == "No fever since yesterday"
    assert fixed.sections["history_present_illness"][0].cites == ["x2"]
    assert not any(i.severity == "block" for i in fixed.issues)
    assert approve(fixed, "Dr Test", AT).version == 2


def test_removing_a_line_renumbers_later_flags_and_lists_an_emptied_section():
    draft = flagged_draft()
    fixed = resolve(draft, [fix("remove_line", "history_present_illness:0", {}),
                            fix("remove_line", "chief_complaints:0", {}).model_copy(update={"id": "r2"})], REF)
    assert [line.text for line in fixed.sections["history_present_illness"]] == ["Dry cough"]
    assert {(i.code, i.target) for i in fixed.issues} == {("section_mismatch", "history_present_illness:0")}
    assert "Complaints" in fixed.not_discussed


def test_finding_flag_stays_while_another_unedited_line_still_uses_it():
    from voicerx.contracts.report import ReportLine
    from voicerx.pipeline.assemble import content_hash

    draft = flagged_draft()
    draft.sections["advice"].append(ReportLine(text="Fever absent", cites=["x2"]))
    draft.content_hash = content_hash(draft)
    fixed = resolve(draft, [fix("edit_line", "history_present_illness:0", {"text": "No fever"})], REF)
    assert ("negation_mismatch", "x2") in {(i.code, i.target) for i in fixed.issues}


def test_line_correction_needs_a_real_line_and_text():
    draft = flagged_draft()
    for correction in (fix("edit_line", "diagnoses:5", {"text": "x"}), fix("edit_line", "nonsense", {"text": "x"}),
                       fix("edit_line", "history_present_illness:0", {"text": "  "})):
        with pytest.raises(ResolutionRefused):
            resolve(draft, [correction], REF)


def omitted_draft():
    # Stage 2 left x2 out, so Check 2 raised a blocking omission nothing could clear (runbook C-47).
    from voicerx.contracts.issues import Issue
    from voicerx.pipeline.assemble import content_hash

    draft = make_draft([resolved_medicine()])
    draft.sections["history_present_illness"] = []
    draft.issues.append(Issue(code="omission", severity="block", target="x2", message="omission"))
    draft.content_hash = content_hash(draft)
    return draft


def test_adding_a_line_for_an_omitted_finding_clears_the_omission():
    fixed = resolve(omitted_draft(), [fix("add_line", "history_present_illness", {"text": "No fever", "cites": ["x2"]})], REF)
    assert [(line.text, line.cites) for line in fixed.sections["history_present_illness"]] == [("No fever", ["x2"])]
    assert "omission" not in codes(fixed) and "History" not in fixed.not_discussed
    assert approve(fixed, "Dr Test", AT).version == 2


def test_dismissing_an_unused_finding_clears_its_flags_but_not_one_still_in_use():
    fixed = resolve(omitted_draft(), [fix("dismiss_item", "x2", {})], REF)
    assert "omission" not in codes(fixed)
    with pytest.raises(ResolutionRefused):
        resolve(omitted_draft(), [fix("dismiss_item", "x1", {})], REF)


def test_added_line_needs_a_known_section_text_and_kept_citations():
    for correction in (fix("add_line", "nonsense", {"text": "x", "cites": []}),
                       fix("add_line", "advice", {"text": " ", "cites": []}),
                       fix("add_line", "advice", {"text": "x", "cites": ["x99"]})):
        with pytest.raises(ResolutionRefused):
            resolve(omitted_draft(), [correction], REF)


def test_a_doctor_setting_a_filled_value_removes_its_mark():
    draft = make_draft([resolved_medicine(filled={'dose': 'standard', 'food': 'standard', 'product': 'auto'})])
    fixed = resolve(draft, [fix("set_dose", "rx1", {"amount": "2", "unit": "tablet"}),
                            fix("choose_product", "rx1", {"product_id": "p-dolo-650"}).model_copy(update={"id": "r2"})], REF)
    assert fixed.checked.medications[0].filled == {'food': 'standard'}
