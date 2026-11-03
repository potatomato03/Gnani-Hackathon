"""Follow-up after approval: the plan, what the patient said, and what the doctor must see.

Design: docs/superpowers/specs/2026-11-02-followup-agent-design.md.
"""
from datetime import date, datetime
from typing import Literal

from typing import Any

from pydantic import Field, PrivateAttr

from .medication import Strict

Channel = Literal["simulated", "whatsapp", "voice"]
TouchKind = Literal["summary", "tolerance", "progress", "end_of_course", "review"]
Question = Literal["tolerance", "symptom_status", "adherence", "review_attendance", "side_effect_detail"]
TaskKind = Literal["urgent", "question", "consult_request", "callback", "no_response", "worse",
                   "stopped_medicine", "side_effect", "document"]
# Most urgent first: the order the doctor's list is sorted in.
TASK_ORDER: tuple[str, ...] = ("urgent", "worse", "side_effect", "stopped_medicine", "question", "document",
                               "callback", "consult_request", "no_response")
# What a model read in a patient's message (runbook D-115). Code validates it; nothing here is ever sent.
Intent = Literal["checkin_answer", "medicine_question", "change_request", "problem", "appointment",
                 "talk_to_doctor", "stop", "greeting", "change_language", "send_report", "other"]
MemoryKind = Literal["answer", "problem", "warning_sign", "question", "request", "document_fact"]


class FollowUpTouch(Strict):
    id: str
    kind: TouchKind
    due_at: datetime
    questions: list[Question] = Field(default_factory=list)
    medicine_ids: list[str] = Field(default_factory=list)
    status: Literal["planned", "sent", "answered", "skipped", "expired"] = "planned"


class FollowUpPlan(Strict):
    visit_ref: str
    report_hash: str
    patient_id: str
    channel: Channel
    language: str
    touches: list[FollowUpTouch]


class FollowUpAnswer(Strict):
    question: Question
    value: str
    quote: str | None = None
    medicine_id: str | None = None


class FollowUpRecord(Strict):
    id: str
    synthetic: Literal[True] = True
    clinic_id: str
    patient_id: str
    visit_ref: str
    report_hash: str
    touch_id: str | None
    channel: Channel
    received_at: datetime
    raw_text: str
    transcript_source: Literal["typed", "prisma", "button", "document"] | None
    answers: list[FollowUpAnswer] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    action: Literal["recorded", "answered", "clarified", "escalated", "urgent", "stopped"]
    reply_text: str
    reply_cites: list[str] = Field(default_factory=list)


class DoctorTask(Strict):
    id: str
    kind: TaskKind
    record_id: str | None
    patient_id: str
    visit_ref: str
    created_at: datetime
    note: str
    status: Literal["open", "done"] = "open"


class Understanding(Strict):
    intent: Intent
    answer_value: str | None
    medicine_id: str | None
    language: Literal["hi-IN", "en-IN"] | None
    warning_signs: list[str]
    quote: str                      # copied from the patient's message; checked by code


class MemoryItem(Strict):
    """One thing the patient told us, kept per patient (runbook D-118). Never a phone number."""
    id: str
    synthetic: Literal[True] = True
    patient_key: str
    visit_ref: str
    kind: MemoryKind
    text: str
    quote: str | None
    source: Literal["typed", "prisma", "button", "call", "document"]
    source_ref: str | None
    at: datetime


class Button(Strict):
    id: str
    label: str


class Message(Strict):
    id: str
    sender: Literal["clinic", "patient"]
    kind: Literal["text", "summary", "question", "answer", "urgent", "system"] = "text"
    text: str
    buttons: list[Button] = Field(default_factory=list)
    at: datetime
    touch_id: str | None = None
    cites: list[str] = Field(default_factory=list)
    # A clinic message voiced by Timbre: the cached audio's name. A patient message that was a voice note.
    audio_id: str | None = None
    voice: bool = False


class Awaiting(Strict):
    touch_id: str
    question: Question
    remaining: list[Question] = Field(default_factory=list)


class Conversation(Strict):
    id: str
    synthetic: Literal[True] = True
    clinic_id: str
    case_id: str
    visit_id: str | None = None     # the approved visit this follow-up runs from (agent/visits.py)
    patient_id: str
    patient_name: str
    doctor_name: str
    clinic_name: str
    language: str
    visit_date: date
    report_hash: str
    consents: list[str]
    plan: FollowUpPlan
    clock: datetime
    messages: list[Message] = Field(default_factory=list)
    records: list[FollowUpRecord] = Field(default_factory=list)
    tasks: list[DoctorTask] = Field(default_factory=list)
    awaiting: Awaiting | None = None
    unanswered: int = 0
    stopped: bool = False
    # Real WhatsApp (private testing, runbook D-113). The phone number is never stored: only a keyed hash of it.
    contact: str | None = None
    delivered: int = 0                       # messages[:delivered] were handed to WhatsApp
    last_inbound_at: datetime | None = None  # wall-clock time of the patient's last message (24-hour window)
    last_inbound_voice: bool = False         # reply with a voice note too when the patient sent one
    language_chosen: bool = True             # False while the first-message language question is open (D-116)
    patient_key: str | None = None           # keyed hash for WhatsApp, "sim-<patient_id>" in the demo (D-118)
    remembered: int = 0                      # records[:remembered] were written to patient memory
    confirm_stop: bool = False               # the model read "stop"; waiting for the patient to confirm
    # The visit (with its approved report) this conversation runs from; not stored with the conversation.
    _visit: Any = PrivateAttr(default=None)
