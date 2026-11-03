from voicerx.contracts.extraction import Extraction
from voicerx.pipeline.extract import PROMPT_VERSION, build_extraction_prompt, extract


class FakeClient:
    def __init__(self):
        self.calls = []

    def generate(self, system, user, schema, prompt_version):
        self.calls.append((system, user, schema, prompt_version))
        return Extraction(items=[], medications=[], corrections=[]), "meta"


def test_transcript_is_fenced_and_copied_verbatim():
    _, user = build_extraction_prompt("बुखार नहीं है।", ["Dolo 650"])
    assert "<<<TRANSCRIPT\nबुखार नहीं है।\nTRANSCRIPT>>>" in user
    assert "Dolo 650" in user


def test_prompt_keeps_laterality_empty_unless_a_side_is_spoken():
    # Both models filled a side for a plural like "tonsils"; qwen3:8b filled one on every item (runbook C-35).
    from voicerx.pipeline.extract import SYSTEM

    assert PROMPT_VERSION == "extract-v5"
    assert "laterality is null unless the quote itself names a side" in SYSTEM
    assert "A plural body part" in SYSTEM


def test_prompt_tells_tests_from_therapy_and_review():
    # Physiotherapy and a later re-examination were extracted as orders and printed under "Tests ordered".
    from voicerx.pipeline.extract import SYSTEM

    assert "physiotherapy" in SYSTEM and "follow_up" in SYSTEM


def test_extract_asks_for_the_extraction_schema_with_the_prompt_version():
    from conftest import REPO_ROOT
    from voicerx.reference import load_reference

    fake = FakeClient()
    result, _ = extract(fake, "No fever.", load_reference(REPO_ROOT))
    assert result.items == []
    assert fake.calls[0][2] is Extraction and fake.calls[0][3] == PROMPT_VERSION


def test_prompt_separates_strength_dose_timing_and_food_and_never_translates():
    # typed-groq-1: strengths ("forty") used as doses, timing and food joined, Telugu phrases translated,
    # and a whole sentence given as a medicine name (runbook C-37).
    from voicerx.pipeline.extract import SYSTEM

    for rule in ("never the strength in the medicine's name", "Never join two fields in one phrase",
                 "name_quote is only the spoken medicine name", "Never translate",
                 "A negative test or sign"):
        assert rule in SYSTEM
