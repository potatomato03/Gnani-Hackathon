from dataclasses import asdict, replace

from conftest import REPO_ROOT
from voicerx.llm.client import QuotaExhausted
from voicerx.pipeline.run import RunResult, current_ids_for, load_case_inputs, run_case
from voicerx.reference import load_reference


def test_case_inputs_carry_no_expected_answers():
    cases = load_case_inputs(REPO_ROOT, "typed")
    assert len(cases) == 25
    assert set(asdict(cases[0])) == {"case_id", "family_id", "encounter_index", "transcript", "patient_id",
                                     "doctor_id", "visit_date", "language"}


def test_typed_cross_talk_case_includes_the_patient_words_without_labels():
    case = next(c for c in load_case_inputs(REPO_ROOT, "typed") if c.case_id == "fam-009-a")
    assert "मुझे चक्कर भी आते हैं" in case.transcript and "[patient]" not in case.transcript


class QuotaAtStageTwo:
    def generate(self, system, user, schema, prompt_version):
        if prompt_version.startswith("report"):
            raise QuotaExhausted("both keys used")
        from voicerx.contracts.extraction import Extraction
        from voicerx.llm.client import CallMeta
        meta = CallMeta(provider="fake", model="fake", prompt_version=prompt_version, cache_key="k", cached=False, key_index=0, attempts=1)
        return Extraction(items=[], medications=[], corrections=[]), meta


def test_quota_mid_run_is_incomplete_with_no_report(tmp_path):
    case = load_case_inputs(REPO_ROOT, "typed")[0]
    result = run_case(case, QuotaAtStageTwo(), load_reference(REPO_ROOT), tmp_path, frozenset())
    assert (result.status, result.stage) == ("incomplete", "write_report")
    assert (tmp_path / "extraction.json").exists()
    assert not (tmp_path / "draft_report.json").exists()


def test_failed_rerun_removes_the_old_report(tmp_path):
    (tmp_path / "draft_report.json").write_text("{}", encoding="utf-8")
    (tmp_path / "report.pdf").write_bytes(b"old")
    case = load_case_inputs(REPO_ROOT, "typed")[0]
    run_case(case, QuotaAtStageTwo(), load_reference(REPO_ROOT), tmp_path, frozenset())
    assert not (tmp_path / "draft_report.json").exists() and not (tmp_path / "report.pdf").exists()


def test_rerun_keeps_signed_and_versioned_files_aside(tmp_path):
    # A cache rebuild deleted fam-008-a's approval, its PDF, FHIR bundles and draft v1 (runbook C-45).
    kept = {"approved_report.json": "{}", "report_approved.pdf": "%PDF", "fhir_op_consult.json": "{}",
            "fhir_prescription.json": "{}", "fhir_status.json": "{}", "draft_report.v1.json": "{}"}
    for name, content in kept.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    (tmp_path / "draft_report.json").write_text("{}", encoding="utf-8")
    case = load_case_inputs(REPO_ROOT, "typed")[0]
    run_case(case, QuotaAtStageTwo(), load_reference(REPO_ROOT), tmp_path, frozenset())
    aside = [d for d in tmp_path.iterdir() if d.is_dir() and d.name.startswith("superseded-")]
    assert len(aside) == 1 and {p.name for p in aside[0].iterdir()} == set(kept)
    assert not any((tmp_path / name).exists() for name in kept)


def test_missing_transcript_is_reported_not_skipped(tmp_path):
    case = replace(load_case_inputs(REPO_ROOT, "typed")[0], transcript=None)
    result = run_case(case, QuotaAtStageTwo(), load_reference(REPO_ROOT), tmp_path, frozenset())
    assert result.status == "missing_input"
    assert len(load_case_inputs(REPO_ROOT, "whisper")) == 25


def test_speech_sources_read_their_own_transcript_folder_and_unknown_ones_fail():
    import pytest

    cases = {c.case_id: c for c in load_case_inputs(REPO_ROOT, "prisma")}
    expected = REPO_ROOT / "data/eval/results/prisma/fam-001-a.txt"
    assert len(cases) == 25
    assert (cases["fam-001-a"].transcript is None) == (not expected.exists())
    with pytest.raises(ValueError, match="source must be one of"):
        load_case_inputs(REPO_ROOT, "deepgram")


def test_variants_of_one_visit_never_chain():
    cases = load_case_inputs(REPO_ROOT, "typed")
    variant_b = next(c for c in cases if c.case_id == "fam-001-b")
    done = {"fam-001-a": RunResult(status="draft", stage=None, error=None, draft=None,
                                   active_ids=frozenset({"p-dolo-650"}))}
    assert current_ids_for(variant_b, done, cases) == (frozenset(), [])


def test_incomplete_earlier_visit_gives_a_warning_and_no_history():
    cases = load_case_inputs(REPO_ROOT, "typed")
    second = next(c for c in cases if c.case_id == "fam-011-v2")
    done = {"fam-011-v1": RunResult(status="incomplete", stage="extract", error="quota", draft=None)}
    ids, issues = current_ids_for(second, done, cases)
    assert ids == frozenset()
    assert [(i.code, i.severity) for i in issues] == [("previous_encounter_incomplete", "warn")]
def test_parallel_families_preserve_visit_order_and_isolate_history(tmp_path, monkeypatch):
    from voicerx.pipeline import run as runner
    cases = [c for c in load_case_inputs(REPO_ROOT, 'typed') if c.family_id in ('fam-010', 'fam-011')]
    seen = {}
    def fake(case, client, reference, out_dir, current_ids, history_issues=()):
        seen[case.case_id] = current_ids
        return RunResult('draft', None, None, None, frozenset({case.case_id}))
    monkeypatch.setattr(runner, 'run_case', fake)
    results = runner.run_cases(cases, None, None, tmp_path, workers=2)
    assert len(results) == 5
    assert seen['fam-010-a'] == seen['fam-010-b'] == seen['fam-011-v1'] == frozenset()
    assert seen['fam-011-v2'] == frozenset({'fam-011-v1'})
    assert seen['fam-011-v3'] == frozenset({'fam-011-v2'})


