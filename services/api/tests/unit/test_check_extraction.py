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
