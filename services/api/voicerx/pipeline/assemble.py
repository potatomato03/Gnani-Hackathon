"""Deterministic presentation and frozen draft assembly."""
from copy import deepcopy
from hashlib import sha256
import json
from ..contracts.medication import Grid, Frequency, AsNeeded, Taper
from ..contracts.report import DraftReport, Header, MedicineRow, MODEL_SECTIONS
from .check_extraction import medicine_issues

DISPLAY_NAMES = dict(zip(MODEL_SECTIONS, ['Complaints', 'History', 'Vitals', 'Examination', 'Results', 'Tests ordered',
    'Diagnosis', 'Advice', 'Referrals', 'Plan', 'Follow-up']))
# How the report reads: the headings of a hospital outpatient summary, each over the stored sections it
# gathers. Storage keeps the eleven sections, so older reports, approvals and exports are unchanged.
REPORT_GROUPS = [('Present problem', ['chief_complaints', 'history_present_illness']),
                 ('Objective findings & investigations', ['vitals', 'examination', 'investigation_results']),
                 ('Assessment', ['diagnoses']), ('Treatment advised', ['advice', 'plan']),
                 ('Tests ordered', ['investigations_ordered']), ('Referrals', ['referrals']), ('Review', ['follow_up'])]
FOOD_TEXT = {'after_food': 'after food', 'before_food': 'before food', 'with_food': 'with food', 'empty_stomach': 'empty stomach'}


def product_label(product):
    form = {'tablet': 'TAB', 'capsule': 'CAP', 'inhaler': 'INHALER'}.get(product.form, product.form)
    ingredients = '+'.join(c.ingredient for c in product.components)
    strengths = '+'.join(c.strength + c.unit for c in product.components)
    return f'{product.brand} {form} ({ingredients}) {strengths}'.upper()


def duration_text(duration):
    return f'{duration.value} {duration.unit}' + ('s' if duration.value != 1 else '')


def dose_text(dose):
    unit = dose.unit + ('s' if dose.amount != '1' and dose.unit in ('tablet', 'capsule', 'puff', 'teaspoon') else '')
    return dose.amount + ' ' + unit


def grid_text(grid):
    return ' and '.join(text for field, text in zip('maen', ['in the morning', 'in the afternoon', 'in the evening', 'at night'])
                        if float(getattr(grid, field)) > 0)


def medicine_row(rx, reference, visit_date):
    if rx.match == 'exact' and rx.product_id in reference.products:
        label = product_label(reference.products[rx.product_id])
    elif rx.match == 'ambiguous':
        label = 'Doctor to choose: ' + ' or '.join(product_label(reference.products[p]) for p in rx.candidate_ids)
    else:
        label = 'Unrecognised medicine: ' + rx.spoken_name
    grid = [getattr(rx.schedule, field) for field in 'maen'] if isinstance(rx.schedule, Grid) else ['-'] * 4
    parts = []
    if isinstance(rx.schedule, Taper):
        parts.append(', then '.join(' '.join(filter(None, [dose_text(s.dose), grid_text(s.when) if s.when else '',
                                                           'for ' + duration_text(s.duration)])) for s in rx.schedule.steps))
    else:
        parts.append(dose_text(rx.dose) if rx.dose else 'quantity not stated')
        if isinstance(rx.schedule, Frequency):
            if rx.schedule.period == 'day':
                parts.append({1: 'once daily, time not specified', 2: 'twice daily, times not specified'}.get(
                    rx.schedule.times, f'{rx.schedule.times} times a day, times not specified'))
            else:
                parts.append(f'{rx.schedule.times} times a week, times not specified')
        elif isinstance(rx.schedule, AsNeeded):
            parts.append('when needed' + (f', at most {rx.schedule.max_per_day} a day' if rx.schedule.max_per_day else ''))
        elif rx.schedule is None:
            parts.append('timing not stated')
    if rx.route:
        parts.append(rx.route)
    parts.append(FOOD_TEXT.get(rx.food, 'food timing not stated'))
    if not isinstance(rx.schedule, Taper):
        parts.append('for ' + duration_text(rx.duration) if rx.duration else 'duration not stated')
    parts.append(rx.start.date.strftime('from %d-%b-%Y (%a)').upper().replace('FROM ', 'from ').replace(
        rx.start.date.strftime('%b').upper(), rx.start.date.strftime('%b')) if rx.start.date else 'start not stated')
    detail = ', '.join(parts)
    detail = detail[0].upper() + detail[1:]
    return MedicineRow(label=label, grid=grid, detail=detail,
                       flags=[i.code for i in medicine_issues([rx], reference, None)])


def table_medicines(checked):
    return [m for m in checked.medications if m.action in ('start', 'change', 'continue')]


def current_medicine_lines(checked, reference):
    labels = {'continue': 'Continuing', 'history': 'Past', 'stop': 'Stopped'}
    return [labels[m.action] + ': ' + medicine_row(m, reference, None).label
            for m in checked.medications if m.action in labels]


def build_header(patient_id, doctor_id, visit_date, reference):
    patient, doctor = reference.patients[patient_id], reference.doctors[doctor_id]
    status = patient['allergy_status']
    allergy = 'Known allergies: ' + ', '.join(patient['allergies']) if status == 'known' else (
        'No known allergies' if status == 'nka' else 'Allergy status not recorded')
    return Header(clinic_name=reference.clinic['name'], doctor_name=doctor['name'], doctor_reg_no=doctor['nmc_reg_no'],
        patient_name=patient['name'], sex=patient['sex'], age=visit_date.year - patient['birth_year'],
        patient_id=patient_id, mrn=patient['mrn'], visit_date=visit_date, allergy_text=allergy)


def content_hash(report):
    payload = report.model_dump(mode='json', exclude={'content_hash', 'status', 'approved_by', 'approved_at'})
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def assemble_draft(case_id, patient_id, doctor_id, visit_date, fields, checked, check2_issues, reference):
    used = {pid for m in checked.medications for pid in [m.product_id, *m.candidate_ids] if pid in reference.products}
    draft = DraftReport(case_id=case_id, version=1, predecessor_hash=None,
        header=build_header(patient_id, doctor_id, visit_date, reference),
        sections={section: deepcopy(getattr(fields, section)) for section in MODEL_SECTIONS},
        current_medicines=current_medicine_lines(checked, reference),
        medicines=[medicine_row(m, reference, visit_date) for m in table_medicines(checked)],
        not_discussed=[DISPLAY_NAMES[s] for s in MODEL_SECTIONS if not getattr(fields, s)],
        checked=checked.model_copy(deep=True), issues=deepcopy(checked.issues + check2_issues),
        language_pref=reference.patients[patient_id]['language_pref'],
        record_snapshot=deepcopy({'patient': reference.patients[patient_id], 'doctor': reference.doctors[doctor_id], 'clinic': reference.clinic}),
        products_used={pid: reference.products[pid].model_copy(deep=True) for pid in used}, resolutions=[], content_hash='')
    draft.content_hash = content_hash(draft)
    return draft
