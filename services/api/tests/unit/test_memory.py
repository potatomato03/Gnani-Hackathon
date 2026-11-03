"""Per-patient memory (runbook D-118): local JSONL store, Supabase fallback, and what a record becomes."""
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from followup_helpers import await_question, dolo, visits  # noqa: F401
from voicerx.agent.conversation import receive
from voicerx.agent.memory import (LocalMemoryStore, SafeMemory, items_from_record, patient_key_for_number,
                                  patient_key_for_simulated)
from voicerx.contracts.documents import PatientDocument, ReportReading
from voicerx.contracts.followup import MemoryItem

T0 = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)


def item(id, patient_key, minute=0, kind="answer"):
    return MemoryItem(id=id, patient_key=patient_key, visit_ref="fam-001-a", kind=kind, text=f"text {id}",
                      quote=None, source="typed", source_ref=None, at=T0 + timedelta(minutes=minute))


def document(patient_key, sha="a" * 64):
    reading = ReportReading(is_medical_report=True, report_type="CBC", report_date=None, transcription="Hb 10",
                            findings=[], medicines_named=[])
    return PatientDocument(id=f"d-{sha[:6]}", patient_key=patient_key, visit_ref="fam-001-a", mime="application/pdf",
                           sha256=sha, pages=1, method="pdf_text", reading=reading, received_at=T0)


class BrokenStore:
    def __init__(self, error):
        self.error = error

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise self.error
        return fail


@pytest.fixture
def dolo_after_worse_and_callback(dolo):
    await_question(dolo, "symptom_status")
    receive(dolo, button="worse")
    receive(dolo, text="DOCTOR")
    return dolo


def test_local_store_keeps_items_per_patient_newest_last(tmp_path):
    store = LocalMemoryStore(tmp_path)
    store.add([item("c", "k1", minute=3), item("b", "k2", minute=2), item("a", "k1", minute=1)])
    assert [i.id for i in store.recent("k1")] == ["a", "c"]
    assert [i.id for i in store.recent("k1", limit=1)] == ["c"]
    assert store.recent("nobody") == []


def test_local_store_keeps_each_document_once(tmp_path):
    store = LocalMemoryStore(tmp_path)
    assert store.add_document(document("k1")) is True
    assert store.add_document(document("k1")) is False
    assert store.add_document(document("k1", sha="b" * 64)) is True
    assert [d.sha256[0] for d in store.documents("k1")] == ["a", "b"]


def test_local_store_refuses_a_key_that_is_not_a_plain_name(tmp_path):
    with pytest.raises(ValueError):
        LocalMemoryStore(tmp_path).add([item("a", "../escape")])


def test_items_from_record_cover_answers_flags_and_escalations(dolo_after_worse_and_callback):
    conv = dolo_after_worse_and_callback
    items = [i for r in conv.records for i in items_from_record(conv, r)]
    kinds = [i.kind for i in items]
    assert {"answer", "problem", "request"} <= set(kinds)
    assert all(i.patient_key == patient_key_for_simulated(conv) for i in items)
    assert len({i.id for i in items}) == len(items)


def test_a_warning_sign_becomes_memory(dolo):
    record = receive(dolo, text="I have chest pain since morning")
    items = items_from_record(dolo, record)
    assert [i.kind for i in items] == ["warning_sign"] and items[0].text == "chest_pain"
    assert items[0].quote == "I have chest pain since morning"


def test_safe_memory_falls_back_when_supabase_fails(tmp_path):
    safe = SafeMemory(BrokenStore(psycopg.OperationalError("paused")), LocalMemoryStore(tmp_path))
    safe.add([item("a", "k1")])
    assert [i.id for i in safe.recent("k1")] == ["a"]
    assert safe.add_document(document("k1")) is True and len(safe.documents("k1")) == 1


def test_patient_key_never_contains_the_number():
    key = patient_key_for_number("910000000001", "secret")
    assert len(key) == 16 and "0000000001" not in key
    assert key == patient_key_for_number("910000000001", "secret") != patient_key_for_number("910000000001", "x")



class EmptyStore:
    """A primary that works but holds nothing: e.g. Supabase after a write fell back to the local store."""

    def add(self, items):
        pass

    def recent(self, patient_key, limit=20):
        return []

    def add_document(self, doc):
        raise psycopg.errors.UntranslatableCharacter("NUL in text")

    def documents(self, patient_key):
        return []


def test_safe_memory_reads_include_what_fell_back(tmp_path):
    local = LocalMemoryStore(tmp_path)
    local.add([item("a", "k1")])
    safe = SafeMemory(EmptyStore(), local)
    assert safe.add_document(document("k1")) is True              # primary refused it; kept locally
    assert [d.sha256[0] for d in safe.documents("k1")] == ["a"]
    assert [i.id for i in safe.recent("k1")] == ["a"]
