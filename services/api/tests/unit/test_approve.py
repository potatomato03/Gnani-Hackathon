from datetime import datetime

import pytest

from voicerx.approve import ApprovalBlocked, HashMismatch, approve
from voicerx.contracts.issues import Issue


def test_draft_with_a_blocking_issue_cannot_be_approved(draft_report):
    blocked = draft_report.model_copy(update={"issues": [Issue(code="missing_quantity", severity="block",
                                                               target="rx1", message="no dose")]})
    with pytest.raises(ApprovalBlocked):
        approve(blocked, "Dr Test", datetime(2026, 10, 5, 12, 0))


def test_approval_needs_a_name(draft_report):
    with pytest.raises(ValueError):
        approve(draft_report, " ", datetime(2026, 10, 5, 12, 0))


def test_approved_report_keeps_the_content_and_records_who_and_when(draft_report):
    approved = approve(draft_report, "Dr Test", datetime(2026, 10, 5, 12, 0))
    assert approved.status == "approved" and approved.version == 1
    assert approved.content_hash == draft_report.content_hash
    assert approved.approved_by == "Dr Test"


def test_draft_altered_outside_the_tools_is_refused(draft_report):
    header = draft_report.header.model_copy(update={"patient_name": "Someone Else"})
    with pytest.raises(HashMismatch):
        approve(draft_report.model_copy(update={"header": header}), "Dr Test", datetime(2026, 10, 5, 12, 0))
def test_cli_reapproval_rechecks_the_current_draft(draft_report, approved_report, tmp_path, monkeypatch):
    import sys
    import pytest
    from voicerx.approve import main, HashMismatch
    draft_report.header.patient_name = 'Altered after approval'
    (tmp_path / 'draft_report.json').write_text(draft_report.model_dump_json(), encoding='utf-8')
    (tmp_path / 'approved_report.json').write_text(approved_report.model_dump_json(), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['approve', str(tmp_path), '--by', approved_report.approved_by])
    with pytest.raises(HashMismatch):
        main()




def test_a_new_approval_keeps_the_earlier_signed_version(draft_report, tmp_path, monkeypatch):
    # Approving again replaced the earlier approved record, PDF and bundles in place (runbook C-46).
    import json
    import sys
    from voicerx.approve import main
    (tmp_path / 'draft_report.json').write_text(draft_report.model_dump_json(), encoding='utf-8')
    for name in ('Dr First', 'Dr Second'):
        monkeypatch.setattr(sys, 'argv', ['approve', str(tmp_path), '--by', name])
        main()
    aside = [d for d in tmp_path.iterdir() if d.is_dir() and d.name.startswith('superseded-')]
    assert len(aside) == 1
    assert json.loads((aside[0] / 'approved_report.json').read_text(encoding='utf-8'))['approved_by'] == 'Dr First'
    assert {'report_approved.pdf', 'fhir_op_consult.json'} <= {p.name for p in aside[0].iterdir()}
    assert json.loads((tmp_path / 'approved_report.json').read_text(encoding='utf-8'))['approved_by'] == 'Dr Second'
