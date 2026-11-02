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
