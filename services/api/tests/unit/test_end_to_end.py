import pytest

from conftest import REPO_ROOT, FixtureClient
from voicerx.pipeline.run import load_case_inputs, run_case
from voicerx.reference import load_reference

REF = load_reference(REPO_ROOT)
FIXTURES = REPO_ROOT / "services/api/tests/fixtures/fam-001-a"
CASE = next(c for c in load_case_inputs(REPO_ROOT, "typed") if c.case_id == "fam-001-a")


def run(tmp_path, mutate=None):
    return run_case(CASE, FixtureClient(FIXTURES, mutate), REF, tmp_path, frozenset())


def blocking(result):
    return {i.code for i in result.draft.issues if i.severity == "block"}


def test_clean_run_gives_a_draft_with_the_right_medicine_and_no_blocks(tmp_path):
    result = run(tmp_path)
    assert result.status == "draft" and blocking(result) == set()
    row = result.draft.medicines[0]
    assert (row.label, row.detail) == ("DOLO 650 TAB (PARACETAMOL) 650MG",
                                       "1 tablet, when needed, after food, for 3 days, start not stated")
    assert (tmp_path / "draft_report.json").exists()


def edit_item(term, **changes):
    def mutate(version, data):
        if version.startswith("extract"):
            for item in data["items"]:
                if item["term"] == term:
                    item.update(changes)
        return data
    return mutate


def edit_medicine(**changes):
    def mutate(version, data):
        if version.startswith("extract"):
            data["medications"][0].update(changes)
        return data
    return mutate


def edit_line(section, text, cites=None):
    def mutate(version, data):
        if version.startswith("report"):
            data[section][0]["text"] = text
            if cites:
                data[section][0]["cites"] = cites
        return data
    return mutate


@pytest.mark.parametrize("name, mutate, code", [
    ("negation dropped from the quote", edit_item("fever", quote="बुखार"), "negation_mismatch"),
    ("negation lost in writing", edit_line("history_present_illness", "Fever"), "negation_mismatch"),
    ("dose changed", edit_medicine(dose_phrase="दो tablet"), "phrase_not_bound"),
    ("strength changed", edit_medicine(spoken_name="Dolo five hundred"), "unmatched_product"),
    ("duration borrowed from another sentence", edit_medicine(duration_phrase="तीन दिन से"), "phrase_not_bound"),
    ("relative's finding written as the patient's", edit_item("fever", subject="family"), "subject_mismatch"),
    ("provisional made definite", edit_line("diagnoses", "Viral pharyngitis"), "certainty_mismatch"),
    ("absent and present in one line",
     edit_line("chief_complaints", "Sore throat for 3 days, no fever", cites=["x1", "x3"]), "mixed_negation"),
    ("speaker unclear", edit_medicine(said_by="unclear"), "speaker_unclear"),
    ("new medicine written as current", edit_line("history_present_illness", "Already taking Dolo 650"),
     "medicine_not_in_source"),
])
def test_sabotage_is_caught(tmp_path, name, mutate, code):
    assert code in blocking(run(tmp_path, mutate)), name
