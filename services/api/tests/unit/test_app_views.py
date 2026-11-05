from datetime import datetime, timezone

import pytest

from conftest import make_draft, resolved_medicine
from voicerx.app.views import CorrectionRefused, build_resolutions, report_view
from voicerx.reference import load_reference
from voicerx.standard import load_rules
from conftest import REPO_ROOT

REF = load_reference(REPO_ROOT)
NOW = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)
ACTOR = {'id': 'doc-001', 'display_name': 'Dr Parth Shan'}


def view(draft, suggestions=None):
    return report_view(draft, encounter_id='enc-1', patient_id='pat-001', organisation_id='clinic-001',
                       catalog=REF.products, capabilities={'resolve': True, 'approve': True},
                       suggestions=suggestions, rules=load_rules(REPO_ROOT))


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


def test_clinical_interpretation_flags_offer_correct_but_medicine_requirements_do_not():
    from voicerx.contracts.issues import Issue
    draft = make_draft([resolved_medicine(dose=None)])
    draft.issues.extend([Issue(code='negation_mismatch', severity='block', target='x1', message='Check negation'),
                         Issue(code='certainty_mismatch', severity='warn', target='chief_complaints:0', message='Check certainty')])
    issues = {i['code']: i for i in view(draft)['issue_views']}
    assert issues['negation_mismatch']['actions'] == ['confirm_interpretation', 'edit_line', 'remove_line']
    assert issues['certainty_mismatch']['actions'] == ['confirm_interpretation', 'edit_line', 'remove_line']
    assert 'confirm_interpretation' not in issues['missing_quantity']['actions']
    [confirmation] = build_resolutions([{'action': 'confirm_interpretation', 'target': 'x1',
        'value': {'code': 'negation_mismatch'}, 'reason': 'Confirmed correct as written by the doctor.'}], ACTOR, NOW)
    assert confirmation.by == 'Dr Parth Shan (doc-001)' and confirmation.at == NOW


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


def test_a_medicine_offers_its_standard_instructions_for_what_was_left_unsaid():
    [med] = view(make_draft([resolved_medicine(dose=None, food=None)]))['medication_views']
    assert {p['action']: p['value'] for p in med['standard']} == {
        'set_dose': {'amount': '1', 'unit': 'tablet'}, 'set_food': {'food': 'after_food'}}


def test_each_suggestion_carries_the_standard_instructions_it_would_bring():
    rx = resolved_medicine(match='unmatched', product_id=None, candidate_ids=[], spoken_name='Pandee', dose=None, food=None)
    pan_d = {'product_id': 'in-2', 'label': 'PAN-D CAP (DOMPERIDONE+PANTOPRAZOLE) 30MG+40MG', 'tier': 'indian',
             'composition': 'Domperidone (30mg) + Pantoprazole (40mg)', 'form': 'capsule'}
    [med] = view(make_draft([rx]), suggestions={'rx1': {'heard': 'Pandee', 'items': [pan_d]}})['medication_views']
    assert med['standard'] == []
    assert {p['action']: p['value'] for p in med['suggestions'][0]['standard']} == {
        'set_dose': {'amount': '1', 'unit': 'capsule'}, 'set_food': {'food': 'before_food'}}


def test_the_view_lists_the_summary_headings_in_order():
    groups = view(make_draft([resolved_medicine()]))['report_groups']
    assert groups[0] == ['Present problem', ['chief_complaints', 'history_present_illness']]


def test_an_instruction_said_away_from_its_medicine_can_be_used_in_one_click():
    rx = resolved_medicine(duration=None, unbound=['duration_phrase'],
                           quotes={'name_quote': 'Dolo six fifty', 'duration_phrase': 'for three days'})
    data = view(make_draft([rx]))
    [card] = [i for i in data['issue_views'] if i['code'] == 'phrase_not_bound']
    assert card['message'] == 'Said away from this medicine: duration “for three days”'
    assert card['uses'] == [{'label': 'Use “for three days”',
                             'item': {'action': 'set_duration', 'value': {'value': 3, 'unit': 'day'}}}]


def test_a_quote_not_in_the_transcript_is_kept_in_the_report_but_not_shown():
    from voicerx.contracts.issues import Issue
    draft = make_draft([resolved_medicine()])
    draft.issues.append(Issue(code='quote_not_found', severity='warn', target='f-dropped', message='quote not found'))
    shown = view(draft)
    assert all(i['code'] != 'quote_not_found' for i in shown['issue_views'])
    assert any(i.code == 'quote_not_found' for i in draft.issues)  # still in the stored report, for audit
