from datetime import date, datetime
from typing import Literal
from pydantic import Field
from .medication import Strict
from .extraction import CheckedExtraction
from .issues import Issue
from ..reference import Product

MODEL_SECTIONS = ["chief_complaints", "history_present_illness", "vitals", "examination", "investigation_results", "investigations_ordered", "diagnoses", "advice", "referrals", "plan", "follow_up"]


class ReportLine(Strict):
    text: str
    cites: list[str]


class ReportFields(Strict):
    chief_complaints: list[ReportLine] = Field(default_factory=list)
    history_present_illness: list[ReportLine] = Field(default_factory=list)
    vitals: list[ReportLine] = Field(default_factory=list)
    examination: list[ReportLine] = Field(default_factory=list)
    investigation_results: list[ReportLine] = Field(default_factory=list)
    investigations_ordered: list[ReportLine] = Field(default_factory=list)
    diagnoses: list[ReportLine] = Field(default_factory=list)
    advice: list[ReportLine] = Field(default_factory=list)
    referrals: list[ReportLine] = Field(default_factory=list)
    plan: list[ReportLine] = Field(default_factory=list)
    follow_up: list[ReportLine] = Field(default_factory=list)


class Header(Strict):
    clinic_name: str
    doctor_name: str
    doctor_reg_no: str
    patient_name: str
    sex: str
    age: int
    patient_id: str
    mrn: str
    visit_date: date
    allergy_text: str


class MedicineRow(Strict):
    label: str
    grid: list[str]
    detail: str
    flags: list[str]


class Resolution(Strict):
    id: str
    action: Literal["choose_product", "set_dose", "set_timing", "set_food", "set_duration", "remove_medicine", "confirm_order", "acknowledge",
                    "edit_line", "remove_line"]
    target: str
    value: dict
    reason: str
    by: str
    at: datetime


class DraftReport(Strict):
    case_id: str
    status: Literal["draft"] = "draft"
    version: int
    predecessor_hash: str | None
    header: Header
    sections: dict[str, list[ReportLine]]
    current_medicines: list[str]
    medicines: list[MedicineRow]
    not_discussed: list[str]
    checked: CheckedExtraction
    issues: list[Issue]
    language_pref: str
    record_snapshot: dict
    products_used: dict[str, Product]
    resolutions: list[Resolution]
    content_hash: str


class ApprovedReport(DraftReport):
    status: Literal["approved"] = "approved"
    approved_by: str
    approved_at: datetime
