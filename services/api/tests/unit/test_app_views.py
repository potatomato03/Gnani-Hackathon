from datetime import datetime, timezone

import pytest

from conftest import make_draft, resolved_medicine
from voicerx.app.views import CorrectionRefused, build_resolutions, report_view
from voicerx.reference import load_reference
from conftest import REPO_ROOT

REF = load_reference(REPO_ROOT)
NOW = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)
ACTOR = {'id': 'doc-001', 'display_name': 'Dr Parth Shan'}


def view(draft):
    return report_view(draft, encounter_id='enc-1', patient_id='pat-001', organisation_id='clinic-001',
                       catalog=REF.products, capabilities={'resolve': True, 'approve': True})


def test_every_issue_is_shown_with_actions_that_fit_its_target():
    draft = make_draft([resolved_medicine(dose=None)])
    issues = {i['code']: i for i in view(draft)['issue_views']}
    assert issues['missing_quantity']['target_kind'] == 'medicine'
    assert 'set_dose' in issues['missing_quantity']['actions'] and 'remove_medicine' in issues['missing_quantity']['actions']
    assert issues['missing_quantity']['severity'] == 'block' and issues['missing_quantity']['title'] == 'Dose not stated'


def test_an_unknown_code_shows_its_message_and_offers_no_shortcut():
    from voicerx.contracts.issues import Issue
    draft = make_draft([resolved_medicine()])
    draft.issues.append(Issue(code='brand_new_check', severity='block', target='report', message='Something new'))
    unknown = next(i for i in view(draft)['issue_views'] if i['code'] == 'brand_new_check')
    assert unknown['title'] == 'Something new' and unknown['actions'] == []


def test_lines_get_stable_refs_and_findings_list_the_lines_citing_them():
    data = view(make_draft([resolved_medicine()]))
    assert {'id': 'chief_complaints:0', 'section': 'chief_complaints', 'index': 0} in data['line_refs']
    assert data['findings']['x1']['cited_by'] == ['chief_complaints:0']


def test_medication_view_carries_typed_fields_and_its_display_row():
    med = view(make_draft([resolved_medicine()]))['medication_views'][0]
    assert med['id'] == 'rx1' and med['product_label'].startswith('DOLO 650 TAB')
    assert med['schedule'] == {'type': 'as_needed', 'max_per_day': None}
    assert med['row']['detail'].startswith('1 tablet, when needed')


def test_blocking_issues_disable_approval_with_a_reason():
    data = view(make_draft([resolved_medicine(dose=None)]))
    assert data['blocking_count'] == 1 and data['can_approve'] is False


def test_resolutions_take_identity_and_time_from_the_server():
    [resolution] = build_resolutions([{'action': 'set_dose', 'target': 'rx1', 'value': {'amount': '1', 'unit': 'tablet'},
                                       'reason': 'Dose confirmed with the patient.'}], ACTOR, NOW)
    assert resolution.by == 'Dr Parth Shan (doc-001)' and resolution.at == NOW and resolution.id


@pytest.mark.parametrize('item, message', [
    ({'action': 'set_dose', 'target': 'rx1', 'value': {'amount': '1'}, 'reason': 'x'}, 'value'),
    ({'action': 'set_dose', 'target': 'rx1', 'value': {'amount': '1', 'unit': 'tablet', 'extra': 1}, 'reason': 'x'}, 'value'),
    ({'action': 'set_dose', 'target': 'rx1', 'value': {'amount': '1', 'unit': 'tablet'}, 'reason': '  '}, 'reason'),
    ({'action': 'delete_everything', 'target': 'rx1', 'value': {}, 'reason': 'x'}, 'action'),
    ({'action': 'add_line', 'target': 'plan', 'value': {'text': 'Review', 'cites': 'x1'}, 'reason': 'x'}, 'value'),
])
def test_malformed_corrections_are_refused_before_reaching_the_engine(item, message):
    with pytest.raises(CorrectionRefused, match=message):
        build_resolutions([item], ACTOR, NOW)


def test_an_empty_batch_is_refused():
    with pytest.raises(CorrectionRefused, match='at least one'):
        build_resolutions([], ACTOR, NOW)
