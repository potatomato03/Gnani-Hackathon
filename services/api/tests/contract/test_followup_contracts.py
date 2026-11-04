import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from voicerx.agent.conversation import start
from voicerx.agent.demo import build_visit
from voicerx.contracts.documents import PatientDocument, ReportFinding, ReportReading
from voicerx.contracts.followup import TASK_ORDER, Conversation, MemoryItem, Understanding

AT = datetime(2026, 11, 4, tzinfo=timezone.utc)
NEW_FIELDS = ("language_chosen", "patient_key", "remembered", "confirm_stop")


@pytest.fixture(scope="module")
def stored_conversation_json(tmp_path_factory):
    conv = start(build_visit("fam-001-a", tmp_path_factory.mktemp("visits")), "c-old")
    data = json.loads(conv.model_dump_json())
    for name in NEW_FIELDS:                         # as saved before these fields existed
        data.pop(name, None)
    return json.dumps(data)


def test_understanding_rejects_unknown_intent_and_extra_fields():
    with pytest.raises(ValidationError):
        Understanding(intent="diagnose", answer_value=None, medicine_id=None, language=None, warning_signs=[],
                      quote="x")
    with pytest.raises(ValidationError):
        Understanding.model_validate({"intent": "other", "answer_value": None, "medicine_id": None,
                                      "language": None, "warning_signs": [], "quote": "x", "advice": "rest"})


def test_memory_and_documents_are_always_synthetic():
    with pytest.raises(ValidationError):
        MemoryItem(id="m1", synthetic=False, patient_key="k", visit_ref="v", kind="answer", text="t",
                   quote=None, source="typed", source_ref=None, at=AT)
    reading = ReportReading(is_medical_report=True, report_type="CBC", report_date="2026-10-01",
                            transcription="Hb 10.2 g/dL",
                            findings=[ReportFinding(name="Hb", value="10.2", unit="g/dL", reference_range=None,
                                                    flag="low", quote="Hb 10.2")],
                            medicines_named=[])
    with pytest.raises(ValidationError):
        PatientDocument(id="d1", synthetic=False, patient_key="k", visit_ref="v", mime="application/pdf",
                        sha256="0" * 64, pages=1, method="pdf_text", reading=reading, received_at=AT)


def test_document_task_sorts_after_question():
    assert TASK_ORDER.index("document") == TASK_ORDER.index("question") + 1


def test_old_conversation_json_still_loads(stored_conversation_json):
    conv = Conversation.model_validate_json(stored_conversation_json)
    assert conv.language_chosen is True and conv.remembered == 0
    assert conv.patient_key is None and conv.confirm_stop is False
