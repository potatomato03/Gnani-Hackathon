from conftest import REPO_ROOT
from voicerx.contracts.extraction import CheckedExtraction, ExtractedItem
from voicerx.contracts.report import ReportFields, ReportLine
from voicerx.pipeline.check_report import check_report
from voicerx.reference import load_reference

REF = load_reference(REPO_ROOT)


def item(id, kind, term, quote, assertion="present", laterality=None, subject="patient", certainty="stated",
         temporality="current"):
    return ExtractedItem(id=id, kind=kind, term=term, quote=quote, assertion=assertion, certainty=certainty,
                         temporality=temporality, laterality=laterality, subject=subject, said_by="doctor")


CHECKED = CheckedExtraction(
    transcript_sha256="x", dropped=[], medications=[], corrections=[], issues=[],
    kept=[item("x1", "symptom", "sore throat for three days", "तीन दिन से गले में दर्द"),
          item("x2", "symptom", "fever", "बुखार नहीं है", assertion="absent"),
          item("x3", "exam", "swelling over the left wrist", "swelling over the left wrist", laterality="left")])


def fields(**sections):
    base = {"chief_complaints": [ReportLine(text="Sore throat for 3 days", cites=["x1"])],
            "history_present_illness": [ReportLine(text="No fever", cites=["x2"])],
            "examination": [ReportLine(text="Swelling over the left wrist", cites=["x3"])]}
    return ReportFields(**{**base, **sections})


def codes(f, checked=CHECKED):
    return {i.code for i in check_report(f, checked, REF)}


def test_faithful_report_has_no_issues():
    assert codes(fields()) == set()


def test_line_without_citations_blocks():
    assert "line_unsupported" in codes(fields(advice=[ReportLine(text="Rest", cites=[])]))


def test_number_not_in_the_cited_item_blocks():
    assert "number_not_in_source" in codes(fields(chief_complaints=[ReportLine(text="Sore throat for 5 days", cites=["x1"])]))


def test_negation_lost_in_writing_blocks():
    assert "negation_mismatch" in codes(fields(history_present_illness=[ReportLine(text="Fever", cites=["x2"])]))


def test_side_lost_in_writing_blocks():
    assert "laterality_mismatch" in codes(fields(examination=[ReportLine(text="Swelling over the wrist", cites=["x3"])]))


def test_side_added_without_evidence_blocks():
    assert 'laterality_mismatch' in codes(fields(chief_complaints=[
        ReportLine(text='Left-sided sore throat for 3 days', cites=['x1'])]))


def test_unknown_assertion_cannot_become_a_positive_finding():
    unknown = CHECKED.model_copy(deep=True)
    unknown.kept[1].assertion = 'unknown'
    unknown.kept[1].quote = 'Fever status unknown'
    assert 'negation_mismatch' in codes(fields(history_present_illness=[
        ReportLine(text='Fever', cites=['x2'])]), unknown)
    assert 'negation_mismatch' not in codes(fields(history_present_illness=[
        ReportLine(text='Fever status unknown', cites=['x2'])]), unknown)


def test_dose_written_into_a_section_blocks():
    assert "dose_in_text" in codes(fields(advice=[ReportLine(text="Take 2 tablets", cites=["x1"])]))


def test_medicine_named_without_a_source_blocks():
    assert "medicine_not_in_source" in codes(fields(advice=[ReportLine(text="Avoid Combiflam", cites=["x1"])]))


def test_finding_filed_under_the_wrong_section_warns():
    assert "section_mismatch" in codes(fields(examination=[], vitals=[ReportLine(text="Swelling over the left wrist", cites=["x3"])]))


def test_item_never_cited_is_an_omission():
    assert "omission" in codes(fields(examination=[]))


def test_item_cited_twice_is_duplication():
    assert "duplication" in codes(fields(history_present_illness=[ReportLine(text="No fever", cites=["x2"]),
                                                                  ReportLine(text="Denies fever", cites=["x2"])]))


def test_empty_extraction_blocks_instead_of_looking_complete():
    empty = CHECKED.model_copy(update={"kept": []})
    assert "nothing_extracted" in codes(ReportFields(), empty)


def plus(*items):
    return CHECKED.model_copy(update={"kept": CHECKED.kept + list(items)})


def test_line_mixing_absent_and_present_items_blocks():
    line = ReportLine(text="Sore throat for 3 days, no fever", cites=["x1", "x2"])
    assert "mixed_negation" in codes(fields(chief_complaints=[line], history_present_illness=[]))


def test_relatives_condition_written_as_the_patients_blocks():
    checked = plus(item("x4", "family_history", "diabetes in mother", "माँ को sugar है", subject="family"))
    hpi = [ReportLine(text="No fever", cites=["x2"])]
    wrong = fields(history_present_illness=hpi + [ReportLine(text="Diabetes", cites=["x4"])])
    right = fields(history_present_illness=hpi + [ReportLine(text="Mother has diabetes", cites=["x4"])])
    assert "subject_mismatch" in codes(wrong, checked)
    assert "subject_mismatch" not in codes(right, checked)


def test_provisional_diagnosis_written_as_confirmed_blocks():
    checked = plus(item("x5", "diagnosis", "viral pharyngitis", "viral pharyngitis लग रहा है", certainty="provisional"))
    wrong = fields(diagnoses=[ReportLine(text="Viral pharyngitis", cites=["x5"])])
    right = fields(diagnoses=[ReportLine(text="Provisional: viral pharyngitis", cites=["x5"])])
    assert "certainty_mismatch" in codes(wrong, checked)
    assert "certainty_mismatch" not in codes(right, checked)


def test_past_history_written_as_current_warns():
    checked = plus(item("x6", "history", "asthma for five years", "Known asthma है, पाँच साल से", temporality="past"))
    hpi = [ReportLine(text="No fever", cites=["x2"]), ReportLine(text="Asthma", cites=["x6"])]
    assert "temporality_mismatch" in codes(fields(history_present_illness=hpi), checked)


def test_conditional_follow_up_keeps_its_negation():
    checked = plus(item("x7", "follow_up", "come back if not better in three days",
                        "तीन दिन में ठीक न हो तो दोबारा दिखाना है", temporality="planned"))
    line = ReportLine(text="Review if not better in 3 days", cites=["x7"])
    assert "negation_mismatch" not in codes(fields(follow_up=[line]), checked)
