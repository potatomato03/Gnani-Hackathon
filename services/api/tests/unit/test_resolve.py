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
