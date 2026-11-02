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

    assert PROMPT_VERSION == "extract-v2"
    assert "laterality is null unless the quote itself names a side" in SYSTEM
    assert "A plural body part" in SYSTEM


def test_extract_asks_for_the_extraction_schema_with_the_prompt_version():
    from conftest import REPO_ROOT
    from voicerx.reference import load_reference

    fake = FakeClient()
    result, _ = extract(fake, "No fever.", load_reference(REPO_ROOT))
    assert result.items == []
    assert fake.calls[0][2] is Extraction and fake.calls[0][3] == PROMPT_VERSION
