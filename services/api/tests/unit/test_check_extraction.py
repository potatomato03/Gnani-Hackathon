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


def test_medicine_dose_cannot_cross_an_unpunctuated_line_boundary():
    checked = run(meds=[med(timing_phrase=None, food_phrase=None, duration_phrase=None)],
                  transcript='Dolo six fifty\none tablet is what the patient suggested')
    assert 'phrase_not_bound' in codes(checked)
    assert checked.medications[0].dose is None


def test_combining_marks_do_not_create_a_hindi_negation_cue():
    from voicerx.pipeline.check_extraction import has_word, NEGATION_WORDS
    assert not has_word('तीन दिन से गले में दर्द', NEGATION_WORDS)
    assert has_word('बुखार नहीं है।', NEGATION_WORDS)


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


def test_a_known_product_cannot_replace_a_different_quoted_medicine():
    checked = run(meds=[med(spoken_name='Pan forty')])
    assert 'unmatched_product' in codes(checked)
    assert checked.medications[0].product_id is None


def test_model_cannot_add_strength_to_a_bare_quoted_name():
    checked = run(meds=[med(spoken_name='Pan forty', name_quote='Pan', timing_phrase=None,
                            food_phrase=None, duration_phrase=None)], transcript='Pan, one tablet.')
    assert 'ambiguous_product' in codes(checked)
    assert checked.medications[0].product_id is None


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


def test_phrase_ending_in_the_sentence_mark_still_binds():
    # fam-010-a: the model copied "…नहीं।" with its full stop, and the mention ends before the mark.
    transcript = "Asthalin inhaler दो puff ज़रूरत पड़ने पर, दिन में चार बार से ज़्यादा नहीं।"
    rx = med(spoken_name="Asthalin", name_quote="Asthalin inhaler", dose_phrase="दो puff",
             timing_phrase="ज़रूरत पड़ने पर, दिन में चार बार से ज़्यादा नहीं।", food_phrase=None, duration_phrase=None)
    checked = run(meds=[rx], transcript=transcript)
    assert "phrase_not_bound" not in codes(checked)
    assert checked.medications[0].schedule is not None


def test_hedged_finding_recorded_as_definite_blocks():
    # typed-groq-2 fam-008-a: "Acid reflux लग रहा है" (seems like acid reflux) came back stated (runbook C-43).
    transcript = "Acid reflux लग रहा है। Impression acute tonsillitis."
    hedged = item(id="x1", kind="symptom", term="acid reflux", quote="Acid reflux लग रहा है।", assertion="present")
    assert "certainty_mismatch" in codes(run([hedged], transcript=transcript))
    assert "certainty_mismatch" not in codes(run([item(**{**hedged.model_dump(), "kind": "diagnosis",
                                                          "certainty": "provisional"})], transcript=transcript))
    stated = item(id="x2", kind="diagnosis", term="acute tonsillitis", quote="Impression acute tonsillitis.",
                  assertion="present")
    assert "certainty_mismatch" not in codes(run([stated], transcript=transcript))


def test_doctor_line_marked_as_patient_speech_is_kept_and_blocked():
    # typed-local-2 fam-005-a: the model called the doctor's Telma order patient speech, and it vanished (C-44).
    transcript = "[doctor] Telma forty दिन में एक बार, तीस दिन तक।\n[patient] मैं Combiflam लेता हूँ।"
    telma = med(spoken_name="Telma forty", name_quote="Telma forty", dose_phrase=None,
                timing_phrase="दिन में एक बार", food_phrase=None, duration_phrase="तीस दिन तक", said_by="patient")
    combiflam = med(id="rx2", spoken_name="Combiflam", name_quote="Combiflam", dose_phrase=None, timing_phrase=None,
                    food_phrase=None, duration_phrase=None, said_by="patient")
    checked = run(meds=[telma, combiflam], transcript=transcript)
    assert [m.id for m in checked.medications] == ["rx1"] and checked.medications[0].speaker_unclear
    assert ("speaker_unclear", "rx1") in {(i.code, i.target) for i in checked.issues}
    assert ("patient_speech", "rx2") in {(i.code, i.target) for i in checked.issues}


def test_unlabelled_order_called_patient_speech_is_kept_unless_said_in_the_first_person():
    # Pipeline transcripts carry no speaker labels, as in fam-005-a's dictation (C-44).
    transcript = "Telma forty दिन में एक बार, तीस दिन तक। मैं तो Combiflam लेता हूँ।"
    telma = med(spoken_name="Telma forty", name_quote="Telma forty", dose_phrase=None,
                timing_phrase="दिन में एक बार", food_phrase=None, duration_phrase="तीस दिन तक", said_by="patient")
    combiflam = med(id="rx2", spoken_name="Combiflam", name_quote="Combiflam", dose_phrase=None, timing_phrase=None,
                    food_phrase=None, duration_phrase=None, said_by="patient")
    checked = run(meds=[telma, combiflam], transcript=transcript)
    assert [m.id for m in checked.medications] == ["rx1"]
    assert {"speaker_unclear", "missing_quantity"} <= {i.code for i in checked.issues if i.target == "rx1"}


def test_verified_name_quote_decides_when_the_spoken_name_matches_nothing():
    # typed-local-2 fam-008-a: the whole sentence came back as the spoken name, though the quote was "Pan" (J-22).
    transcript = "Pan एक गोली सुबह खाली पेट, दो हफ़्ते।"
    rx = med(spoken_name="Pan एक गोली सुबह खाली पेट, दो हफ़्ते", name_quote="Pan", dose_phrase="एक गोली",
             timing_phrase="सुबह", food_phrase="खाली पेट", duration_phrase="दो हफ़्ते")
    checked = run(meds=[rx], transcript=transcript)
    assert checked.medications[0].match == "ambiguous" and "ambiguous_product" in codes(checked)


def test_spoken_name_found_verbatim_outranks_a_shorter_quote():
    # typed-groq-2 fam-011-v3: name quote "Amlong" (5 mg) against spoken "Amlong two point five" (C-52).
    transcript = "Amlong two point five, एक tablet रात को, तीस दिन।"
    rx = med(spoken_name="Amlong two point five", name_quote="Amlong", dose_phrase="एक tablet",
             timing_phrase="रात को", food_phrase=None, duration_phrase="तीस दिन")
    resolved = run(meds=[rx], transcript=transcript).medications[0]
    assert (resolved.match, resolved.product_id) == ("exact", "p-amlong-2-5")


def test_padded_spoken_name_never_becomes_exact_through_its_quote():
    # The J-22 fallback must not pick Amlong 5 for a padded "Amlong two point five, एक tablet…" (C-52).
    transcript = "Amlong two point five, एक tablet रात को, तीस दिन।"
    rx = med(spoken_name="Amlong two point five एक tablet रात को", name_quote="Amlong", dose_phrase="एक tablet",
             timing_phrase="रात को", food_phrase=None, duration_phrase="तीस दिन")
    assert run(meds=[rx], transcript=transcript).medications[0].product_id != "p-amlong-5"


def test_taper_takes_its_food_rule_from_its_own_phrase():
    # typed-groq-2 fam-010: the taper phrase said "खाने के बाद" but food stayed empty (runbook C-54).
    transcript = "Wysolone ten, पहले तीन दिन दो tablet सुबह खाने के बाद, फिर तीन दिन एक tablet सुबह खाने के बाद।"
    rx = med(spoken_name="Wysolone ten", name_quote="Wysolone ten", dose_phrase=None, food_phrase=None,
             timing_phrase="पहले तीन दिन दो tablet सुबह खाने के बाद, फिर तीन दिन एक tablet सुबह खाने के बाद",
             duration_phrase=None)
    resolved = run(meds=[rx], transcript=transcript).medications[0]
    assert isinstance(resolved.schedule, Taper) and resolved.food == "after_food"


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


def test_a_meal_phrase_alone_sets_food_and_slot():
    # Only a food phrase was said, as in "<medicine> before breakfast".
    checked = run(meds=[med(timing_phrase=None, food_phrase="before breakfast")],
                  transcript="Dolo six fifty, one tablet before breakfast for three days.")
    rx = checked.medications[0]
    assert rx.food == "before_food" and rx.schedule.model_dump() == {"type": "grid", "m": "1", "a": "0", "e": "0", "n": "0"}
    assert "food_phrase" not in rx.unresolved and "unparsed_food" not in codes(checked)


def test_once_a_day_with_a_meal_becomes_that_slot():
    checked = run(meds=[med(timing_phrase="once a day", food_phrase="post-lunch")],
                  transcript="Dolo six fifty, one tablet once a day post-lunch for three days.")
    rx = checked.medications[0]
    assert rx.food == "after_food" and rx.schedule.model_dump() == {"type": "grid", "m": "0", "a": "1", "e": "0", "n": "0"}


def test_twice_daily_with_one_meal_keeps_the_frequency():
    checked = run(meds=[med(timing_phrase="twice daily", food_phrase="after dinner")],
                  transcript="Dolo six fifty, one tablet twice daily after dinner for three days.")
    assert checked.medications[0].schedule == Frequency(times=2, period="day")


def test_a_slot_that_contradicts_the_meal_stays_as_said_and_is_flagged():
    checked = run(meds=[med(timing_phrase="at night", food_phrase="after breakfast")],
                  transcript="Dolo six fifty, one tablet at night after breakfast for three days.")
    rx = checked.medications[0]
    assert rx.schedule.model_dump() == {"type": "grid", "m": "0", "a": "0", "e": "0", "n": "1"}
    assert "timing_phrase" in rx.unresolved and "unparsed_timing" in codes(checked)


# Real dictations put the dose before the name, or in the next sentence, and lump timing with duration
# (runbook C-70); the medicine's own window still ends at the next medicine.
def test_a_dose_said_just_before_the_name_belongs_to_it():
    transcript = "Take one Pan D before breakfast for five days."
    rx = run(meds=[med(spoken_name="Pan D", name_quote="Pan D", dose_phrase="one", timing_phrase=None,
                       food_phrase="before breakfast", duration_phrase="for five days")], transcript=transcript).medications[0]
    assert rx.unbound == [] and rx.quotes["dose_phrase"] == "one"


def test_instructions_in_the_next_sentence_belong_to_the_medicine_named_before():
    transcript = "The dosage for Dolo six fifty is... One after breakfast and one after dinner for three days."
    checked = run(meds=[med(dose_phrase="One", timing_phrase="after breakfast and after dinner for three days",
                            food_phrase=None, duration_phrase=None)], transcript=transcript)
    rx = checked.medications[0]
    assert rx.unbound == []
    assert (rx.schedule.m, rx.schedule.a, rx.schedule.e, rx.schedule.n) == ("1", "0", "0", "1")
    assert rx.food == "after_food" and rx.duration == Duration(value=3, unit="day")


def test_the_window_still_stops_at_the_next_medicine():
    transcript = "Dolo six fifty after food. Pan D one before breakfast."
    rx = run(meds=[med(dose_phrase="one", timing_phrase=None, duration_phrase=None)], transcript=transcript).medications[0]
    assert "dose_phrase" in rx.unbound


def test_a_doctor_saying_i_recommend_is_not_an_unclear_speaker():
    transcript = "I am recommending Dolo six fifty, one tablet twice daily after food for three days."
    assert run(meds=[med()], transcript=transcript).medications[0].speaker_unclear is False


def test_a_nukta_written_or_left_out_is_the_same_word():
    transcript = "Dolo six fifty एक tablet जरूरत पड़ने पर खाने के बाद।"
    rx = run(meds=[med(dose_phrase="एक tablet", timing_phrase="ज़रूरत पड़ने पर", food_phrase="खाने के बाद",
                       duration_phrase=None)], transcript=transcript).medications[0]
    assert rx.unbound == []


def test_a_form_word_after_the_name_still_lets_the_next_sentence_count():
    transcript = "Start Dolo six fifty tablet. One tablet twice daily after food for three days."
    rx = run(meds=[med(dose_phrase="One tablet")], transcript=transcript).medications[0]
    assert rx.unbound == []


def test_a_second_spelling_of_the_same_medicine_carries_its_instructions():
    # Speech recognition may spell one medicine two ways in a dictation (runbook C-71).
    transcript = ("Start a painkiller such as Combiflam. Along with Dolo six fifty, Combyflam will be taken for three "
                  "days two times a day.")
    meds = [med(id="rx1", spoken_name="Combiflam", name_quote="Combiflam", dose_phrase=None,
                timing_phrase="two times a day", food_phrase=None, duration_phrase="for three days"),
            med(id="rx2", dose_phrase=None, timing_phrase=None, food_phrase=None, duration_phrase=None)]
    rx = run(meds=meds, transcript=transcript).medications[0]
    assert rx.unbound == [] and rx.duration == Duration(value=3, unit="day")


def test_a_medicine_does_not_take_the_instructions_said_for_the_one_before_it():
    transcript = "Dolo six fifty will be taken for three days once after lunch, and Pan forty before breakfast."
    meds = [med(timing_phrase="once after lunch", food_phrase=None, dose_phrase=None),
            med(id="rx2", spoken_name="Pan forty", name_quote="Pan forty", dose_phrase=None, timing_phrase=None,
                food_phrase="before breakfast", duration_phrase="for three days")]
    pan = run(meds=meds, transcript=transcript).medications[1]
    assert "duration_phrase" in pan.unbound


def test_a_side_said_in_the_quotes_own_sentence_supports_it():
    transcript = "Patient को left knee में pain और instability है। Right shoulder normal."
    checked = run([item(id="x1", kind="symptom", term="pain in left knee", quote="pain और instability है",
                        assertion="present", laterality="left")], transcript=transcript)
    assert "laterality_mismatch" not in codes(checked)
    wrong = run([item(id="x1", kind="symptom", term="pain in right knee", quote="pain और instability है",
                      assertion="present", laterality="right")], transcript=transcript)
    assert "laterality_mismatch" in codes(wrong)


def test_instructions_in_devanagari_english_are_read_and_bound():
    transcript = "स्टार्ट डोलो कैप्सूल से। वन कैप्सूल ओरली लेनी है और ब्रेकफास्ट के पहले पाँच दिन के लिए लेनी है।"
    rx = run(meds=[med(spoken_name="डोलो कैप्सूल", name_quote="डोलो कैप्सूल", dose_phrase="वन कैप्सूल",
                       timing_phrase="ओरली", food_phrase="ब्रेकफास्ट के पहले", duration_phrase="पाँच दिन")],
             transcript=transcript).medications[0]
    assert rx.unbound == []
    assert rx.dose == Dose(amount="1", unit="capsule") and rx.food == "before_food"
    assert rx.duration == Duration(value=5, unit="day") and rx.route == "orally"
    assert (rx.schedule.m, rx.schedule.n) == ("1", "0")


def test_gujarati_negation_and_sides_are_read():
    transcript = "હમણાં એમને fever નથી. ડાબા ઘૂંટણમાં દુખાવો છે."
    checked = run([item(id="x1", term="fever", quote="એમને fever નથી", assertion="absent"),
                   item(id="x2", kind="symptom", term="pain in left knee", quote="ડાબા ઘૂંટણમાં દુખાવો છે",
                        assertion="present", laterality="left")], transcript=transcript)
    assert {"negation_mismatch", "laterality_mismatch"} & codes(checked) == set()


def test_gujarati_linking_words_let_the_next_sentence_count():
    transcript = "જો fever આવે તો Dolo six fifty લેવી છે. One tablet daily after lunch."
    rx = run(meds=[med(dose_phrase="One tablet", timing_phrase="daily", food_phrase="after lunch",
                       duration_phrase=None)], transcript=transcript).medications[0]
    assert rx.unbound == []
