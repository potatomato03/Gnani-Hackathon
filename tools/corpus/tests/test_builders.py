import pandas as pd
import pytest

from build_formulary import find_product, parse_components
from make_seed import build_patients


def dataset(rows):
    return pd.DataFrame(rows, columns=["name", "Is_discontinued"])


def test_product_lookup_ignores_case():
    found = find_product(dataset([("PAN 40 Tablet", False)]), "Pan 40 Tablet")
    assert found["name"] == "PAN 40 Tablet"


def test_discontinued_product_is_never_used():
    with pytest.raises(ValueError):
        find_product(dataset([("Pan 40 Tablet", True)]), "Pan 40 Tablet")


def test_available_row_wins_over_a_discontinued_duplicate():
    rows = dataset([("Pan 40 Tablet", True), ("Pan 40 Tablet", False)])
    assert find_product(rows, "Pan 40 Tablet")["Is_discontinued"] == False  # noqa: E712


@pytest.mark.parametrize(
    "first, second, want",
    [
        (
            "Amoxycillin  (500mg) ",
            " Clavulanic Acid (125mg)",
            [
                {"ingredient": "Amoxycillin", "strength": "500", "unit": "mg"},
                {"ingredient": "Clavulanic Acid", "strength": "125", "unit": "mg"},
            ],
        ),
        (
            "Telmisartan (40mg) ",
            " Hydrochlorothiazide (12.5mg)",
            [
                {"ingredient": "Telmisartan", "strength": "40", "unit": "mg"},
                {"ingredient": "Hydrochlorothiazide", "strength": "12.5", "unit": "mg"},
            ],
        ),
        ("Thyroxine (50mcg)", None, [{"ingredient": "Thyroxine", "strength": "50", "unit": "mcg"}]),
    ],
)
def test_components_keep_exact_strengths(first, second, want):
    assert parse_components(first, second) == want


def test_nan_second_component_is_ignored():
    got = parse_components("Paracetamol (650mg)", float("nan"))
    assert got == [{"ingredient": "Paracetamol", "strength": "650", "unit": "mg"}]


def test_composition_without_a_strength_is_rejected():
    with pytest.raises(ValueError):
        parse_components("Paracetamol", None)


def test_seed_is_repeatable():
    assert build_patients(30) == build_patients(30)


def test_seed_keeps_the_details_a_case_depends_on():
    patients = {record["patient_id"]: record for record in build_patients(30)}
    assert patients["pat-012"]["allergy_status"] == "known"
    assert patients["pat-012"]["allergies"] == ["penicillin"]
    assert patients["pat-006"]["allergy_status"] == "unknown"
    assert len(patients) == 30
