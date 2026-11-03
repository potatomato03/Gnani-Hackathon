"""A report the patient sent (PDF or photo), as read for the doctor (runbook D-119). The file itself is never kept."""
from datetime import datetime
from typing import Literal

from .medication import Strict


class ReportFinding(Strict):
    name: str
    value: str
    unit: str | None
    reference_range: str | None
    flag: Literal["high", "low", "normal", "abnormal"] | None
    quote: str                      # must appear in the transcription, or the finding is dropped


class ReportReading(Strict):
    is_medical_report: bool
    report_type: str | None
    report_date: str | None         # YYYY-MM-DD as printed on the report, or null
    transcription: str
    findings: list[ReportFinding]
    medicines_named: list[str]


class PatientDocument(Strict):
    id: str
    synthetic: Literal[True] = True
    patient_key: str
    visit_ref: str
    mime: str
    sha256: str
    pages: int | None
    method: Literal["pdf_text", "gemini_vision"]
    reading: ReportReading
    received_at: datetime
