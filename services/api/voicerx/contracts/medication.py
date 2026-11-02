"""Lossless medication values. Missing values are represented by None."""
from datetime import date as Date
from decimal import Decimal
import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Dose(Strict):
    amount: StrictStr
    unit: str

    @field_validator("amount")
    @classmethod
    def positive_decimal(cls, value):
        if not re.fullmatch(r"\d+(?:\.\d+)?", value) or Decimal(value) <= 0:
            raise ValueError("dose must be a positive decimal string")
        return value


class Duration(Strict):
    value: int = Field(gt=0)
    unit: Literal["day", "week", "month"]


class Frequency(Strict):
    type: Literal["frequency"] = "frequency"
    times: int = Field(gt=0)
    period: Literal["day", "week"]


class Grid(Strict):
    type: Literal["grid"] = "grid"
    m: StrictStr
    a: StrictStr
    e: StrictStr
    n: StrictStr

    @field_validator("m", "a", "e", "n")
    @classmethod
    def nonnegative_decimal(cls, value):
        if not re.fullmatch(r"\d+(?:\.\d+)?", value):
            raise ValueError("slot must be a nonnegative decimal string")
        return value


class AsNeeded(Strict):
    type: Literal["as_needed"] = "as_needed"
    max_per_day: int | None = Field(default=None, gt=0)


class TaperStep(Strict):
    dose: Dose
    duration: Duration
    when: Grid | None = None


class Taper(Strict):
    type: Literal["taper"] = "taper"
    steps: list[TaperStep] = Field(min_length=2)


Schedule = Annotated[Frequency | Grid | AsNeeded | Taper, Field(discriminator="type")]
Food = Literal["before_food", "after_food", "with_food", "empty_stomach"]


class Start(Strict):
    condition: Literal["unstated", "today", "tomorrow", "date"] = "unstated"
    date: Date | None = None
