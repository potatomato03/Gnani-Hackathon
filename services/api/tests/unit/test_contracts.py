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
