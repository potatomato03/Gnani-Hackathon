"""The message a patient gets the moment the doctor approves (runbook D-140)."""
from voicerx.app.journey import visit_complete_text


def test_visit_complete_text_names_patient_doctor_and_clinic_and_promises_the_report(draft_report):
    header = draft_report.header
    text = visit_complete_text(draft_report)
    assert header.patient_name in text and header.doctor_name in text and header.clinic_name in text
    assert 'is complete' in text and 'few minutes' in text
    assert len(text) < 1024  # well inside WhatsApp's text limit
