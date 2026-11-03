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
    ("thrice daily", Frequency(type="frequency", times=3, period="day")),
    ("QID", Frequency(type="frequency", times=4, period="day")),
    ("roz", Frequency(type="frequency", times=1, period="day")),
    ("रोज़", Frequency(type="frequency", times=1, period="day")),
    ("HS", Grid(type="grid", m="0", a="0", e="0", n="1")),
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


@pytest.mark.parametrize("phrase, want", [
    # A cap or a negated food word is part of the instruction, not a self-correction (runbook C-48).
    ("when needed, not more than four times a day", AsNeeded(type="as_needed", max_per_day=4)),
    ("ज़रूरत पड़ने पर, दिन में चार बार से ज़्यादा नहीं, खाने के बाद", AsNeeded(type="as_needed", max_per_day=4)),
])
def test_a_cap_is_never_cut_off_as_a_correction(phrase, want):
    assert parse_timing(phrase) == want


def test_real_corrections_still_keep_only_the_new_value():
    assert parse_duration("five days, sorry, three days, not five") == Duration(value=3, unit="day")
    assert parse_duration("पाँच दिन, नहीं, तीन दिन") == Duration(value=3, unit="day")


# Meal phrases name both a food rule and a slot (spec 2026-11-03, part A).
@pytest.mark.parametrize("phrase, food, slots", [
    ("before breakfast", "before_food", "m"),
    ("post-lunch", "after_food", "a"),
    ("once a day post-lunch", "after_food", "a"),
    ("after dinner", "after_food", "n"),
    ("pre-lunch", "before_food", "a"),
    ("with breakfast", "with_food", "m"),
    ("after supper", "after_food", "n"),
    ("नाश्ते से पहले", "before_food", "m"),
    ("रात के खाने के बाद", "after_food", "n"),
    ("दोपहर के खाने के बाद", "after_food", "a"),
    ("breakfast के बाद", "after_food", "m"),
    ("breakfast के पहले", "before_food", "m"),
    ("after breakfast and after dinner", "after_food", "mn"),
])
def test_meal_phrases_give_food_and_slot(phrase, food, slots):
    from voicerx.pipeline.schedule import parse_meal
    assert parse_food(phrase) == food
    assert parse_meal(phrase) == (food, set(slots))


@pytest.mark.parametrize("phrase", ["before breakfast and after dinner", "breakfast", "after food", "", None])
def test_mixed_or_mealless_phrases_give_no_meal(phrase):
    from voicerx.pipeline.schedule import parse_meal
    assert parse_meal(phrase) is None


# Gujarati (runbook D-121).
@pytest.mark.parametrize("phrase, want", [
    ("દિવસમાં બે વાર", Frequency(type="frequency", times=2, period="day")),
    ("સવારે", Grid(type="grid", m="1", a="0", e="0", n="0")),
    ("સવારે અને રાત્રે", Grid(type="grid", m="1", a="0", e="0", n="1")),
    ("રોજ", Frequency(type="frequency", times=1, period="day")),
    ("જરૂર પડે તો", AsNeeded(type="as_needed")),
])
def test_gujarati_timing(phrase, want):
    assert parse_timing(phrase) == want


def test_gujarati_dose_duration_food_and_meals():
    from voicerx.pipeline.schedule import parse_meal
    assert parse_dose("એક ગોળી") == Dose(amount="1", unit="tablet")
    assert parse_duration("પાંચ દિવસ") == Duration(value=5, unit="day")
    assert parse_food("જમ્યા પછી") == "after_food" and parse_food("ખાલી પેટે") == "empty_stomach"
    assert parse_meal("નાસ્તા પહેલાં") == ("before_food", {"m"})
    assert parse_meal("before નાસ્તા") == ("before_food", {"m"})


def test_a_number_word_inside_a_gujarati_word_is_not_a_number():
    # "છ" is six, but "છે" is "is".
    assert words_to_digits("fever નથી છે") == "fever નથી છે"
    assert words_to_digits("છ મહિના") == "6 મહિના"
