import json

from voicerx.contracts.extraction import CheckedExtraction, ExtractedItem
from voicerx.pipeline.write_report import build_report_prompt


def test_stage_two_sees_only_checked_items_never_the_transcript():
    kept = [ExtractedItem(id="x1", kind="symptom", term="fever", quote="बुखार नहीं है", assertion="absent",
                          certainty="stated", temporality="current", laterality=None, subject="patient",
                          said_by="doctor")]
    checked = CheckedExtraction(transcript_sha256="x", kept=kept, dropped=[], medications=[], corrections=[], issues=[])
    _, user = build_report_prompt(checked)
    payload = json.loads(user.split("<<<ITEMS\n", 1)[1].split("\nITEMS>>>", 1)[0])
    assert payload == [{"id": "x1", "kind": "symptom", "term": "fever", "assertion": "absent", "certainty": "stated",
                        "temporality": "current", "laterality": None, "subject": "patient"}]
    assert "बुखार" not in user


def test_prompt_writes_provisional_only_for_provisional_items():
    # typed-groq-1 put "Provisional:" on four plainly stated diagnoses (runbook C-37).
    from voicerx.pipeline.write_report import PROMPT_VERSION, SYSTEM

    assert PROMPT_VERSION == "report-v3"
    assert "Never write 'Provisional' for a stated item" in SYSTEM


def test_prompt_asks_for_connected_sentences_without_added_meaning():
    from voicerx.pipeline.write_report import SYSTEM

    assert "The patient presents with" in SYSTEM and "one fact per line" not in SYSTEM.lower()
    assert "never add causes" in SYSTEM
