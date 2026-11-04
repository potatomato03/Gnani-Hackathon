"""Shared fixtures for the conversational follow-up tests (understanding, routing, language, memory)."""
import pytest

from voicerx.agent.conversation import BUTTONS, advance, receive, start
from voicerx.agent.demo import build_visit
from voicerx.contracts.followup import Understanding
from voicerx.pipeline.assemble import table_medicines


@pytest.fixture(scope="module")
def visits(tmp_path_factory):
    out = tmp_path_factory.mktemp("visits")
    return {case: build_visit(case, out) for case in ("fam-001-a", "fam-004-a", "fam-010-a")}


@pytest.fixture
def dolo(visits):
    return start(visits["fam-001-a"], "c-dolo")


def await_question(conv, question):
    for _ in range(12):
        if conv.awaiting and conv.awaiting.question == question:
            return conv
        if conv.awaiting:
            receive(conv, button=BUTTONS[conv.awaiting.question][0])
        elif not advance(conv):
            break
    raise AssertionError(f"the plan never asks {question}")


@pytest.fixture
def dolo_awaiting_symptom_status(dolo):
    return await_question(dolo, "symptom_status")


def medicine_id(conv):
    """The exact-matched medicine of a one-medicine visit."""
    [rx] = [m for m in table_medicines(conv._visit.approved.checked) if m.match == "exact" and m.product_id]
    return rx.id


def understood(**fields):
    base = dict(intent="other", answer_value=None, medicine_id=None, language=None, warning_signs=[], quote="")
    return Understanding(**{**base, **fields})


def fixed(**fields):
    """An nlu callable that always reads the message the same way."""
    reading = understood(**fields)
    return lambda conv, text: reading


def last(conv, sender="clinic"):
    return [m for m in conv.messages if m.sender == sender][-1]


def task_kinds(conv):
    return [t.kind for t in conv.tasks]
