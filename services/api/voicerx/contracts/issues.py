from typing import Literal
from .medication import Strict


class Issue(Strict):
    code: str
    severity: Literal["block", "warn"]
    target: str
    message: str
