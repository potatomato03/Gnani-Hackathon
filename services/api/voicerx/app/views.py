"""The report envelope the browser reads (DESIGN.md section 6) and the corrections it may send (section 7).

The canonical report passes through unchanged; everything the screen needs besides it sits beside it.
"""
from uuid import uuid4

from ..contracts.report import MODEL_SECTIONS, Resolution
from ..pipeline.assemble import DISPLAY_NAMES, product_label, table_medicines

SCHEMA_VERSION = 1
TITLES = {
    'unmatched_product': 'Medicine not recognised', 'ambiguous_product': 'Choose the exact product',
    'fuzzy_product_match': 'Check the medicine name', 'missing_quantity': 'Dose not stated',
    'allergy_conflict': 'Conflicts with a recorded allergy', 'speaker_unclear': 'Not clear who said this',
    'phrase_not_bound': 'An instruction may belong to another medicine', 'unparsed_dose': 'Dose could not be read',
    'unparsed_timing': 'Timing could not be read', 'unparsed_food': 'Food instruction could not be read',
    'unparsed_duration': 'Duration could not be read', 'unparsed_start': 'Start could not be read',
    'unparsed_route': 'Route could not be read', 'quote_not_found': 'Quote not found in the transcript',
    'patient_speech': 'Said by the patient, not the doctor', 'negation_mismatch': 'Present or absent may be wrong',
    'certainty_mismatch': 'Certainty may be wrong', 'laterality_mismatch': 'Side may be wrong',
    'omission': 'Finding left out of the report', 'duplication': 'Finding used more than once',
    'nothing_extracted': 'Nothing was extracted', 'line_unsupported': 'Line has no source',
    'number_not_in_source': 'Number not in the source', 'medicine_not_in_source': 'Medicine not in the source',
    'dose_in_text': 'Dose written into the text', 'mixed_negation': 'Line mixes present and absent findings',
    'subject_mismatch': 'Whose finding is this?', 'temporality_mismatch': 'Past or current?',
    'section_mismatch': 'Possibly the wrong section', 'previous_encounter_incomplete': 'Previous visit incomplete',
}
MEDICINE_ACTIONS = {
    'unmatched_product': ['choose_product'], 'ambiguous_product': ['choose_product'],
    'fuzzy_product_match': ['choose_product'], 'allergy_conflict': ['choose_product'],
    'missing_quantity': ['set_dose'], 'speaker_unclear': ['confirm_order'],
    'phrase_not_bound': ['set_dose', 'set_timing', 'set_food', 'set_duration'],
    'unparsed_dose': ['set_dose'], 'unparsed_timing': ['set_timing'], 'unparsed_food': ['set_food'],
    'unparsed_duration': ['set_duration'],
}
# Each correction's value, exactly: field name -> accepted Python types.
VALUE_SHAPES = {
    'choose_product': {'product_id': str}, 'set_dose': {'amount': str, 'unit': str},
    'set_timing': {'schedule': dict}, 'set_food': {'food': str}, 'set_duration': {'value': int, 'unit': str},
    'remove_medicine': {}, 'confirm_order': {}, 'acknowledge': {'code': str}, 'edit_line': {'text': str},
    'remove_line': {}, 'add_line': {'text': str, 'cites': list}, 'dismiss_item': {},
}


class CorrectionRefused(ValueError):
    pass


def _target_kind(target, medication_ids, finding_ids):
    section, _, index = target.partition(':')
    if section in MODEL_SECTIONS and index.isdigit():
        return 'line'
    if target in medication_ids:
        return 'medicine'
    if target in finding_ids:
        return 'finding'
    return 'report'


def _actions(issue, kind, cited_by):
    actions = []
    if kind == 'medicine':
        actions = MEDICINE_ACTIONS.get(issue.code, []) + (['remove_medicine'] if issue.code in TITLES else [])
    elif kind == 'line' and issue.code in TITLES:
        actions = ['edit_line', 'remove_line']
    elif kind == 'finding' and issue.code in TITLES:
        # A finding no line uses can be dismissed or written up; one in use is corrected through its lines.
        actions = ['edit_line', 'remove_line'] if cited_by else ['add_line', 'dismiss_item']
    if issue.severity == 'warn':
        actions.append('acknowledge')
    return actions


def report_view(report, encounter_id, patient_id, organisation_id, catalog, capabilities, approval=None, artifacts=(),
                suggestions=None):
    medication_ids = {m.id for m in report.checked.medications}
    cited_by = {}
    line_refs = []
    for section in MODEL_SECTIONS:
        for index, line in enumerate(report.sections.get(section, [])):
            ref = f'{section}:{index}'
            line_refs.append({'id': ref, 'section': section, 'index': index})
            for cite in line.cites:
                cited_by.setdefault(cite, []).append(ref)
    findings = {item.id: {**item.model_dump(mode='json'), 'cited_by': cited_by.get(item.id, [])} for item in report.checked.kept}
    issue_views = []
    for number, issue in enumerate(report.issues):
        kind = _target_kind(issue.target, medication_ids, findings)
        issue_views.append({'uid': f'i{number}', 'code': issue.code, 'severity': issue.severity, 'target': issue.target,
                            'target_kind': kind, 'title': TITLES.get(issue.code, issue.message), 'message': issue.message,
                            'lines': cited_by.get(issue.target, []) if kind == 'finding' else [],
                            'actions': _actions(issue, kind, cited_by.get(issue.target))})
    products = {**catalog, **report.products_used}
    rows = dict(zip((m.id for m in table_medicines(report.checked)), report.medicines))
    medication_views = []
    for rx in report.checked.medications:
        medication_views.append({
            **rx.model_dump(mode='json'),
            'product_label': product_label(products[rx.product_id]) if rx.product_id in products else None,
            'candidates': [{'id': pid, 'label': product_label(products[pid])} for pid in rx.candidate_ids if pid in products],
            'row': rows[rx.id].model_dump(mode='json') if rx.id in rows else None,
            'issue_uids': [v['uid'] for v in issue_views if v['target'] == rx.id],
            # Offered only while the doctor still has to choose; once a product is set they are history.
            'suggestions': (suggestions or {}).get(rx.id, {}).get('items', []) if rx.match != 'exact' else []})
    blocking = sum(i.severity == 'block' for i in report.issues)
    return {
        'schema_version': SCHEMA_VERSION, 'encounter_id': encounter_id, 'patient_id': patient_id,
        'organisation_id': organisation_id, 'status': report.status, 'version': report.version,
        'content_hash': report.content_hash, 'report': report.model_dump(mode='json'),
        'section_names': DISPLAY_NAMES, 'line_refs': line_refs, 'findings': findings,
        'medication_views': medication_views, 'issue_views': issue_views, 'blocking_count': blocking,
        'can_approve': report.status == 'draft' and blocking == 0 and bool(capabilities.get('approve')),
        'capabilities': capabilities, 'approval': approval, 'artifacts': list(artifacts),
        'catalog': [{'id': pid, 'label': product_label(p)} for pid, p in sorted(catalog.items())],
    }


def build_resolutions(items, actor, now):
    """Validate each requested correction's shape, then stamp it with the signed-in actor and the server's time."""
    if not items:
        raise CorrectionRefused('at least one correction is required')
    resolutions = []
    for item in items:
        action = item.get('action')
        if action not in VALUE_SHAPES:
            raise CorrectionRefused(f'unknown action: {action!r}')
        value, shape = item.get('value'), VALUE_SHAPES[action]
        if not isinstance(value, dict) or set(value) != set(shape) or not all(
                isinstance(value[k], t) and not isinstance(value[k], bool) for k, t in shape.items()):
            raise CorrectionRefused(f'{action} needs a value of exactly {sorted(shape)}')
        if action == 'add_line' and not all(isinstance(c, str) for c in value['cites']):
            raise CorrectionRefused('add_line value cites must be finding ids')
        if not isinstance(item.get('target'), str) or not item['target'].strip():
            raise CorrectionRefused('a target is required')
        if not isinstance(item.get('reason'), str) or not item['reason'].strip():
            raise CorrectionRefused('a reason is required for every correction')
        resolutions.append(Resolution(id=str(uuid4()), action=action, target=item['target'], value=value,
                                      reason=item['reason'].strip(), by=f"{actor['display_name']} ({actor['id']})", at=now))
    return resolutions
