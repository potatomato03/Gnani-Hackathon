from typing import Literal
from pydantic import Field, model_validator
from .medication import Strict, Dose, Schedule, Food, Duration, Start
from .issues import Issue

Kind = Literal["symptom", "history", "family_history", "exam", "vital", "result", "order", "diagnosis", "advice", "referral", "plan", "follow_up", "allergy"]
Action = Literal["start", "continue", "change", "stop", "history"]


class ExtractedItem(Strict):
    id: str
    kind: Kind
    term: str
    quote: str = Field(min_length=1)
    assertion: Literal["present", "absent", "unknown"]
    certainty: Literal["stated", "provisional", "rule_out"]
    temporality: Literal["current", "past", "planned"]
    laterality: Literal["left", "right", "bilateral"] | None
    subject: Literal["patient", "family", "other"]
    said_by: Literal["doctor", "patient", "unclear"]


class ExtractedMedication(Strict):
    id: str
    action: Action
    spoken_name: str
    name_quote: str = Field(min_length=1)
    dose_phrase: str | None
    timing_phrase: str | None
    food_phrase: str | None
    duration_phrase: str | None
    start_phrase: str | None
    route_phrase: str | None
    said_by: Literal["doctor", "patient", "unclear"]


class ExtractedCorrection(Strict):
    target_id: str
    field: str
    old_quote: str
    new_quote: str


class Extraction(Strict):
    items: list[ExtractedItem]
    medications: list[ExtractedMedication]
    corrections: list[ExtractedCorrection]

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [x.id for x in self.items + self.medications]
        if len(ids) != len(set(ids)):
            raise ValueError("item and medication ids must be unique")
        return self


class DroppedItem(Strict):
    item: ExtractedItem
    reason: str


class ResolvedMedication(Strict):
    id: str
    action: Action
    spoken_name: str
    match: Literal["exact", "ambiguous", "unmatched"]
    product_id: str | None
    candidate_ids: list[str]
    dose: Dose | None
    schedule: Schedule | None
    food: Food | None
    duration: Duration | None
    start: Start
    route: str | None
    unresolved: list[str]
    quotes: dict[str, str]
    fuzzy: bool = False
    speaker_unclear: bool = False
    unbound: list[str] = Field(default_factory=list)


class CheckedExtraction(Strict):
    transcript_sha256: str
    kept: list[ExtractedItem]
    dropped: list[DroppedItem]
    medications: list[ResolvedMedication]
    corrections: list[ExtractedCorrection]
    issues: list[Issue]
