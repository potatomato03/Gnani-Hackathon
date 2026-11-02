"""Models for synthetic case families. A null field means the case does not state it."""

from datetime import date as Date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

Section = Literal[
    "chief_complaints",
    "history_present_illness",
    "current_medications",
    "vitals",
    "examination",
    "investigation_results",
    "investigations_ordered",
    "diagnoses",
    "advice",
    "referrals",
    "plan",
    "follow_up",
]
Language = Literal["english", "hindi", "hinglish", "telugu", "tamil"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fact(Strict):
    id: str
    kind: Literal[
        "symptom",
        "history",
        "family_history",
        "exam",
        "vital",
        "result",
        "order",
        "diagnosis",
        "advice",
        "referral",
        "plan",
        "follow_up",
        "allergy",
    ]
    text: str
    subject: Literal["patient", "family", "other"] = "patient"
    assertion: Literal["present", "absent", "unknown"] = "present"
    certainty: Literal["stated", "provisional", "rule_out"] = "stated"
    temporality: Literal["current", "past", "planned"] = "current"
    laterality: Optional[Literal["left", "right", "bilateral"]] = None
    attribution: Literal["patient_report", "clinician_exam", "clinician_statement", "unknown"]
    section: Section
    delivery: Literal["spoken", "chart", "unavailable"] = "spoken"
    allow_negation_cue: bool = False


class Dose(Strict):
    amount: StrictStr
    unit: str

    @field_validator("amount")
    @classmethod
    def amount_is_positive(cls, value):
        try:
            positive = Decimal(value) > 0
        except InvalidOperation as error:
            raise ValueError("dose amount must be a number written as text") from error
        if not positive:
            raise ValueError("use null for an unknown dose, never zero")
        return value


class Duration(Strict):
    value: int = Field(gt=0)
    unit: Literal["day", "week", "month"]


class Frequency(Strict):
    type: Literal["frequency"]
    times: int = Field(gt=0)
    period: Literal["day", "week"]


class Grid(Strict):
    type: Literal["grid"]
    m: StrictStr
    a: StrictStr
    e: StrictStr
    n: StrictStr


class AsNeeded(Strict):
    type: Literal["as_needed"]
    max_per_day: Optional[int] = None


class TaperStep(Strict):
    dose: Dose
    duration: Duration
    when: Optional[Grid] = None


class Taper(Strict):
    type: Literal["taper"]
    steps: list[TaperStep] = Field(min_length=2)


Schedule = Annotated[Union[Frequency, Grid, AsNeeded, Taper], Field(discriminator="type")]


class Start(Strict):
    condition: Literal["unstated", "today", "tomorrow", "date"] = "unstated"
    date: Optional[Date] = None


class Medication(Strict):
    id: str
    action: Literal["start", "continue", "change", "stop", "history"] = "start"
    spoken_name: str
    match: Literal["exact", "ambiguous", "out_of_formulary"]
    product_id: Optional[str] = None
    candidate_ids: list[str] = []
    dose: Optional[Dose] = None
    route: Optional[str] = None
    schedule: Optional[Schedule] = None
    food: Optional[Literal["before_food", "after_food", "with_food", "empty_stomach"]] = None
    duration: Optional[Duration] = None
    start: Start = Start()


class Utterance(Strict):
    id: str
    speaker: Literal["doctor", "patient", "other"]
    text: str
    supports: list[str] = []
    filler: bool = False


class Correction(Strict):
    target: str
    field: str
    old_value: str
    new_value: str
    old_quote: str
    new_quote: str


class Withheld(Strict):
    id: str
    reason: str
    forbidden_terms: list[str] = Field(min_length=1)


class Trap(Strict):
    id: str
    quote: str
    must_not_become: str


class Variant(Strict):
    variant_id: str
    differs_in: str = Field(min_length=1)
    overrides: dict[str, dict] = {}
    omit: list[str] = []
    utterances: list[Utterance] = Field(min_length=1)
    evidence: dict[str, str]
    corrections: list[Correction] = []
    withheld: list[Withheld] = []
    traps: list[Trap] = []
    expected_flags: list[str] = []


class Encounter(Strict):
    encounter_id: str
    date: Date
    doctor_id: str
    facts: list[Fact]
    medications: list[Medication] = []
    variants: list[Variant] = Field(min_length=1)


class AgentQuestion(Strict):
    id: str
    encounter_id: str
    variant_id: Optional[str] = None
    language: Language
    text: str
    expected_action: Literal["answer", "clarify", "escalate", "urgent"]
    allowed_claims: list[str] = []
    forbidden_claims: list[str] = []


class TimelineStep(Strict):
    after_encounter: str
    active: list[str]
    stopped: list[str]


class Provenance(Strict):
    author: str
    generation_version: str
    reference_version: str
    annotation_version: int
    source_and_license: str
    source_parent_id: Optional[str] = None


class Review(Strict):
    status: Literal["generated", "auto_checked", "human_reviewed", "adjudicated", "released"]
    reviewed_by: Optional[str] = None
    clinical_review: Literal["pending", "approved", "not_needed"] = "pending"
    language_review: Literal["pending", "approved"] = "pending"


class Family(Strict):
    family_id: str
    synthetic: Literal[True]
    track: Literal["everyday", "challenge"]
    specialty: Literal["general_medicine", "orthopaedics"]
    language: Language
    capture_mode: Literal["dictation", "consultation"]
    scenario_tags: list[str] = Field(min_length=1)
    patient_id: str
    timezone: Literal["Asia/Kolkata"]
    expected_behaviour: list[str] = Field(min_length=1)
    provenance: Provenance
    review: Review
    encounters: list[Encounter] = Field(min_length=1)
    agent_questions: list[AgentQuestion]
    timeline: list[TimelineStep] = []
