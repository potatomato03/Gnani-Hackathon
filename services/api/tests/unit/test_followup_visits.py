import json
from datetime import date

import pytest

from voicerx import approve as approve_cli
from voicerx.agent import visits as visits_mod
from voicerx.agent.demo import build_visit
from voicerx.agent.visits import find_approved_visits, load_visit, start_followup, stored_conversations
from voicerx.fixture_client import FixtureClient
from voicerx.pipeline.run import REPO_ROOT, load_case_inputs, run_case
from voicerx.reference import load_reference

FIXTURES = REPO_ROOT / "services/api/tests/fixtures"


def draft_run(runs, case_id="fam-010-a", run_id="typed-demo"):
    """A real pipeline run that stops at a draft, the way the doctor finds it before approval."""
    case = next(c for c in load_case_inputs(REPO_ROOT, "typed") if c.case_id == case_id)
    folder = runs / run_id / case_id
    result = run_case(case, FixtureClient(FIXTURES / case_id), load_reference(REPO_ROOT), folder, frozenset())
    assert result.status == "draft"
    return folder


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(visits_mod, "STATE", tmp_path / "state")
    return tmp_path / "state"


def test_approval_with_followup_starts_exactly_one_conversation(tmp_path, state, capsys):
    folder = draft_run(tmp_path / "runs")
    approve_cli.main([str(folder), "--by", "Dr Lavanya Deshpande", "--review-date", "2026-10-26", "--followup"])
    out = capsys.readouterr().out
    assert "Follow-up started" in out and "Review date confirmed: 2026-10-26" in out
    conversations = stored_conversations(state)
    assert len(conversations) == 1
    conv = conversations[0]
    assert conv.messages[0].kind == "summary" and conv.case_id == "fam-010-a"
    review = json.loads((folder / "followup.json").read_text(encoding="utf-8"))
    assert review["review_date"] == "2026-10-26" and review["confirmed_by"] == "Dr Lavanya Deshpande"
    assert any(t.kind == "review" for t in conv.plan.touches)
    visit = load_visit(folder / "approved_report.json")
    again = start_followup(visit, state)
    assert again.id == conv.id and len(stored_conversations(state)) == 1          # idempotent
    assert start_followup(visit, state, restart=True).id != conv.id


def test_approval_without_followup_starts_nothing(tmp_path, state):
    folder = draft_run(tmp_path / "runs")
    approve_cli.main([str(folder), "--by", "Dr Lavanya Deshpande"])
    assert stored_conversations(state) == [] and not (folder / "followup.json").exists()
    assert load_visit(folder / "approved_report.json").review_date is None


def test_followup_is_refused_when_the_frozen_record_has_no_consent(tmp_path, state, capsys):
    folder = draft_run(tmp_path / "runs")
    draft = json.loads((folder / "draft_report.json").read_text(encoding="utf-8"))
    draft["record_snapshot"]["patient"]["consents"] = ["recording", "ai_processing", "call"]
    from voicerx.contracts.report import DraftReport
    from voicerx.pipeline.assemble import content_hash
    model = DraftReport.model_validate(draft)
    model = model.model_copy(update={"content_hash": content_hash(model)})
    (folder / "draft_report.json").write_text(model.model_dump_json(), encoding="utf-8")
    approve_cli.main([str(folder), "--by", "Dr Lavanya Deshpande", "--followup"])
    assert "Follow-up not started: no consent" in capsys.readouterr().out
    assert stored_conversations(state) == []


def test_scan_finds_demo_and_real_approvals_and_skips_the_rest(tmp_path):
    runs = tmp_path / "runs"
    build_visit("fam-001-a", runs / "followup-demo" / "visits")
    folder = draft_run(runs)
    approve_cli.main([str(folder), "--by", "Dr Lavanya Deshpande"])
    old = runs / "typed-demo" / "fam-010-a" / "superseded-20261019T000000Z"
    old.mkdir()
    (old / "approved_report.json").write_text((folder / "approved_report.json").read_text(encoding="utf-8"), encoding="utf-8")
    tampered = runs / "typed-demo" / "fam-010-b"
    tampered.mkdir()
    report = json.loads((folder / "approved_report.json").read_text(encoding="utf-8"))
    report["medicines"][0]["detail"] = "4 tablets"            # changed after approval
    (tampered / "approved_report.json").write_text(json.dumps(report), encoding="utf-8")
    found, problems = find_approved_visits(runs)
    assert sorted((v.source, v.case_id) for v in found) == [("demo", "fam-001-a"), ("run", "fam-010-a")]
    assert len({v.visit_id for v in found}) == 2
    assert [p["reason"] for p in problems] == ["approved report does not match its fingerprint"]


def test_visit_reads_consent_and_review_date_from_what_was_approved(tmp_path):
    visit = build_visit("fam-010-a", tmp_path / "followup-demo" / "visits")
    assert "followup_whatsapp" in visit.consents
    assert visit.review_date == date(2026, 10, 26) and visit.clinic_id == "clinic-001"
