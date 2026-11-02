"""FHIR R4 documents using pinned ABDM 6.5.0 example codes, not officially validated."""
from html import escape
from uuid import uuid5, NAMESPACE_URL
from ..contracts.medication import Frequency, Grid, AsNeeded, Taper
from ..pipeline.assemble import table_medicines, product_label, content_hash

BASE = 'https://nrces.in/ndhm/fhir/r4/StructureDefinition/'
SYSTEM = 'http://snomed.info/sct'
CODES = {'complaints': ('422843007', 'Chief complaint section'), 'allergies': ('722446000', 'Allergy record'),
    'history': ('371529009', 'History and physical report'), 'orders': ('721963009', 'Order document'),
    'medicines': ('721912009', 'Medication summary document'), 'plan': ('736271009', 'Outpatient care plan')}


def coding(code, display):
    return {'coding': [{'system': SYSTEM, 'code': code, 'display': display}]}


def narrative(lines):
    return {'status': 'generated', 'div': '<div xmlns="http://www.w3.org/1999/xhtml">' +
            ''.join('<p>' + escape(line) + '</p>' for line in lines) + '</div>'}


def dosage(rx, detail):
    def dose(value):
        return {'doseQuantity': {'value': float(value.amount), 'unit': value.unit}}
    def when(grid):
        return [code for field, code in zip('maen', ['MORN', 'AFT', 'EVE', 'NIGHT']) if float(getattr(grid, field)) > 0]
    if isinstance(rx.schedule, Taper):
        result = []
        for index, step in enumerate(rx.schedule.steps, 1):
            repeat = {'boundsDuration': {'value': step.duration.value, 'unit': step.duration.unit,
                'system': 'http://unitsofmeasure.org', 'code': {'day': 'd', 'week': 'wk', 'month': 'mo'}[step.duration.unit]}}
            if step.when:
                repeat['when'] = when(step.when)
            result.append({'sequence': index, 'text': detail, 'doseAndRate': [dose(step.dose)], 'timing': {'repeat': repeat}})
        return result
    result = {'text': detail}
    if rx.dose:
        result['doseAndRate'] = [dose(rx.dose)]
    if isinstance(rx.schedule, Frequency):
        result['timing'] = {'repeat': {'frequency': rx.schedule.times, 'period': 1,
            'periodUnit': 'd' if rx.schedule.period == 'day' else 'wk'}}
    elif isinstance(rx.schedule, Grid):
        result['timing'] = {'repeat': {'when': when(rx.schedule)}}
    elif isinstance(rx.schedule, AsNeeded):
        result['asNeededBoolean'] = True
    if rx.route:
        result['route'] = {'text': rx.route}
    if rx.food:
        result['additionalInstruction'] = [{'text': rx.food.replace('_', ' ')}]
    return [result]


def build_bundles(report):
    if report.status != 'approved':
        raise ValueError('only approved records can be exported')
    if content_hash(report) != report.content_hash:
        raise ValueError('approved record fingerprint differs')
    frozen = report.record_snapshot
    entries = {}
    def uid(key):
        return str(uuid5(NAMESPACE_URL, report.case_id + ':' + key))
    def ref(key):
        return {'reference': 'urn:uuid:' + uid(key)}
    def add(key, kind, **fields):
        resource = {'resourceType': kind, 'id': uid(key), 'meta': {'profile': [BASE + kind]}, **fields}
        entries[key] = {'fullUrl': 'urn:uuid:' + uid(key), 'resource': resource}
        return ref(key)
    patient = frozen['patient']
    add('patient', 'Patient', identifier=[{'system': 'urn:voicerx:synthetic:mrn', 'value': patient['mrn']}],
        name=[{'text': patient['name']}], gender={'M': 'male', 'F': 'female'}.get(patient['sex'], 'unknown'),
        birthDate=str(patient['birth_year']))
    doctor = frozen['doctor']
    add('doctor', 'Practitioner', name=[{'text': doctor['name']}],
        identifier=[{'system': 'urn:voicerx:synthetic:registration', 'value': doctor['nmc_reg_no']}])
    add('clinic', 'Organization', name=frozen['clinic']['name'])
    add('encounter', 'Encounter', status='finished', **{'class': {'system': 'http://terminology.hl7.org/CodeSystem/v3-ActCode', 'code': 'AMB'}},
        subject=ref('patient'), serviceProvider=ref('clinic'), participant=[{'individual': ref('doctor')}],
        period={'start': report.header.visit_date.isoformat()})
    groups = {key: [] for key in CODES}
    for index, allergy in enumerate(patient['allergies'] if patient['allergy_status'] == 'known' else []):
        groups['allergies'].append(add('allergy:' + str(index), 'AllergyIntolerance', patient=ref('patient'),
            code={'text': allergy}, clinicalStatus={'coding': [{'system': 'http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical', 'code': 'active'}]}))
    for item in report.checked.kept:
        if item.assertion != 'present' or item.subject != 'patient':
            continue
        key = 'fact:' + item.id
        if item.kind == 'diagnosis':
            status = {'stated': 'confirmed', 'provisional': 'provisional', 'rule_out': 'differential'}[item.certainty]
            groups['history'].append(add(key, 'Condition', subject=ref('patient'), encounter=ref('encounter'), code={'text': item.term},
                verificationStatus={'coding': [{'system': 'http://terminology.hl7.org/CodeSystem/condition-ver-status', 'code': status}]}))
        elif item.kind in ('exam', 'vital', 'result'):
            groups['history'].append(add(key, 'Observation', status='final', subject=ref('patient'), encounter=ref('encounter'),
                code={'text': item.term}, valueString=item.term))
        elif item.kind in ('order', 'referral'):
            groups['orders'].append(add(key, 'ServiceRequest', status='active', intent='order', subject=ref('patient'),
                requester=ref('doctor'), encounter=ref('encounter'), code={'text': item.term}))
    requests = []
    for rx, row in zip(table_medicines(report.checked), report.medicines):
        requests.append(add('request:' + rx.id, 'MedicationRequest', status='active', intent='order',
            subject=ref('patient'), requester=ref('doctor'), encounter=ref('encounter'), authoredOn=report.header.visit_date.isoformat(),
            medicationCodeableConcept={'text': row.label}, dosageInstruction=dosage(rx, row.detail)))
    groups['medicines'] += requests
    for rx in report.checked.medications:
        if rx.action in ('continue', 'history', 'stop'):
            label = product_label(report.products_used[rx.product_id]) if rx.product_id in report.products_used else rx.spoken_name
            groups['medicines'].append(add('statement:' + rx.id, 'MedicationStatement',
                status={'continue': 'active', 'history': 'completed', 'stop': 'stopped'}[rx.action],
                subject=ref('patient'), context=ref('encounter'), medicationCodeableConcept={'text': label}))
    text_groups = {'complaints': [], 'allergies': [report.header.allergy_text], 'history': report.current_medicines[:], 'orders': [], 'medicines': [], 'plan': []}
    for section, lines in report.sections.items():
        group = 'complaints' if section == 'chief_complaints' else 'orders' if section in ('investigations_ordered', 'referrals') else 'plan' if section in ('advice', 'plan', 'follow_up') else 'history'
        text_groups[group].extend(line.text for line in lines)
    text_groups['medicines'] = [row.label + ': ' + row.detail for row in report.medicines]
    bundles = {}
    for kind in ['op_consult'] + (['prescription'] if report.medicines else []):
        prescription = kind == 'prescription'
        type_code = coding('440545006', 'Prescription record') if prescription else coding('371530004', 'Clinical consultation report')
        type_code['text'] = 'Prescription record' if prescription else 'Clinical Consultation report'
        sections = []
        if prescription:
            sections = [{'title': 'Prescription record', 'code': coding('440545006', 'Prescription record'),
                         'text': narrative(text_groups['medicines']), 'entry': requests}]
        else:
            for group, refs in groups.items():
                if not refs and not text_groups[group]:
                    continue
                section = {'title': CODES[group][1], 'code': coding(*CODES[group]), 'text': narrative(text_groups[group])}
                if refs:
                    section['entry'] = refs
                sections.append(section)
        composition = {'resourceType': 'Composition', 'id': uid(kind + ':composition'),
            'meta': {'profile': [BASE + ('PrescriptionRecord' if prescription else 'OPConsultRecord')]},
            'status': 'final', 'type': type_code, 'subject': ref('patient'), 'encounter': ref('encounter'),
            'date': report.approved_at.isoformat(), 'author': [ref('doctor')], 'custodian': ref('clinic'),
            'title': 'SYNTHETIC DATA - ' + type_code['text'], 'section': sections,
            'text': narrative(['SYNTHETIC DATA', f'Version {report.version}; SHA-256 {report.content_hash}', 'Not officially validated'])}
        # A prescription carries only who, where and the medicine requests; the consult carries everything.
        included = [e for key, e in entries.items()
                    if not prescription or key in ('patient', 'doctor', 'clinic', 'encounter') or key.startswith('request:')]
        bundles[kind] = {'resourceType': 'Bundle', 'id': uid(kind + ':bundle'), 'type': 'document',
            'meta': {'profile': [BASE + 'DocumentBundle']}, 'timestamp': report.approved_at.isoformat(),
            'identifier': {'system': 'urn:voicerx:synthetic:report', 'value': f'{report.case_id}:{report.version}:{report.content_hash}:{kind}'},
            'entry': [{'fullUrl': 'urn:uuid:' + composition['id'], 'resource': composition}, *included]}
    return bundles
