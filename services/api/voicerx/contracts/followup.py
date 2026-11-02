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
                   "stopped_medicine", "side_effect"]
# Most urgent first: the order the doctor's list is sorted in.
TASK_ORDER: tuple[str, ...] = ("urgent", "worse", "side_effect", "stopped_medicine", "question", "callback",
                               "consult_request", "no_response")


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
    transcript_source: Literal["typed", "prisma", "button"] | None
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
    # The visit (with its approved report) this conversation runs from; not stored with the conversation.
    _visit: Any = PrivateAttr(default=None)
