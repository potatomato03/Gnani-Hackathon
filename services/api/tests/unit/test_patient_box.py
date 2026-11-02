from conftest import REPO_ROOT
from voicerx.contracts.medication import Dose, Duration, Grid, Taper, TaperStep
from voicerx.exports.patient_box import build_patient_box

TEMPLATES = REPO_ROOT / "services/api/voicerx/exports/templates/lang"


def test_hindi_row_comes_from_the_fixed_templates(draft_report):
    box = build_patient_box(draft_report.model_copy(update={"language_pref": "hi-IN"}), TEMPLATES)
    assert box.rows == ["DOLO 650: 1 गोली, ज़रूरत पड़ने पर, खाने के बाद, 3 दिन"]
    assert box.reviewed is False and box.note == "अनुवाद की अभी जाँच नहीं हुई है।"


def test_unknown_values_tell_the_patient_to_ask_the_doctor(draft_report):
    rx = draft_report.checked.medications[0].model_copy(update={"dose": None})
    checked = draft_report.checked.model_copy(update={"medications": [rx]})
    box = build_patient_box(draft_report.model_copy(update={"language_pref": "hi-IN", "checked": checked}), TEMPLATES)
    assert box.rows[0].startswith("DOLO 650: डॉक्टर से पूछें,")


def test_taper_row_keeps_each_steps_time_of_day(draft_report):
    morning = Grid(type="grid", m="1", a="0", e="0", n="0")
    steps = [TaperStep(dose=Dose(amount=a, unit="tablet"), duration=Duration(value=3, unit="day"), when=morning)
             for a in ("2", "1")]
    rx = draft_report.checked.medications[0].model_copy(
        update={"dose": None, "duration": None, "schedule": Taper(type="taper", steps=steps)})
    checked = draft_report.checked.model_copy(update={"medications": [rx]})
    box = build_patient_box(draft_report.model_copy(update={"language_pref": "hi-IN", "checked": checked}), TEMPLATES)
    assert box.rows == ["DOLO 650: 2 गोली सुबह 3 दिन, फिर 1 गोली सुबह 3 दिन, खाने के बाद"]


def test_english_patients_get_no_box(draft_report):
    assert build_patient_box(draft_report.model_copy(update={"language_pref": "en-IN"}), TEMPLATES) is None


def test_every_language_file_fills_every_placeholder(draft_report):
    for language in ("te-IN", "ta-IN"):
        box = build_patient_box(draft_report.model_copy(update={"language_pref": language}), TEMPLATES)
        assert box.rows and all("{" not in row for row in box.rows)


def hindi_box(draft_report, **changes):
    rx = draft_report.checked.medications[0].model_copy(update=changes)
    checked = draft_report.checked.model_copy(update={"medications": [rx]})
    return build_patient_box(draft_report.model_copy(update={"language_pref": "hi-IN", "checked": checked}), TEMPLATES)


def test_unit_missing_from_the_template_is_printed_as_itself(draft_report):
    # A 5 ml dose printed as "5 डॉक्टर से पूछें" (runbook C-50).
    assert hindi_box(draft_report, dose=Dose(amount="5", unit="ml")).rows[0].startswith("DOLO 650: 5 ml,")


def test_unresolved_medicine_row_names_the_medicine(draft_report):
    # fam-008-a's draft showed two identical "ask the doctor" lines (runbook C-50).
    box = hindi_box(draft_report, match="unmatched", product_id=None, candidate_ids=[],
                    quotes={"name_quote": "Mucaine gel"})
    assert box.rows == ["Mucaine gel: डॉक्टर से पूछें"]
