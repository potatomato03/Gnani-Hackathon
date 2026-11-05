from datetime import date

import pytest

from conftest import REPO_ROOT, FixtureClient
from voicerx.app.clinical import STEPS, StageFailed, initial_steps, process_typed, reference_for
from voicerx.pipeline.run import load_case_inputs
from voicerx.reference import load_reference

REF = load_reference(REPO_ROOT)
FIXTURES = REPO_ROOT / 'services/api/tests/fixtures/fam-001-a'
CASE = next(c for c in load_case_inputs(REPO_ROOT, 'typed') if c.case_id == 'fam-001-a')


def test_typed_input_skips_transcription_and_starts_with_everything_else_pending():
    steps = initial_steps('typed')
    assert steps[0] == {'key': 'transcribing', 'state': 'skipped'}
    assert [s['key'] for s in steps[1:]] == STEPS[1:] and all(s['state'] == 'pending' for s in steps[1:])


def test_a_typed_source_becomes_a_checked_draft_and_reports_each_stage():
    seen = []
    reference = reference_for(REF, REF.patients[CASE.patient_id], REF.doctors[CASE.doctor_id], REF.clinic)
    draft = process_typed('enc-1', CASE.transcript, CASE.patient_id, CASE.doctor_id, date(2026, 11, 3), FixtureClient(FIXTURES),
                          reference, frozenset(), lambda key, state: seen.append((key, state)))
    assert draft.status == 'draft' and draft.version == 1 and draft.case_id == 'enc-1'
    assert draft.header.visit_date == date(2026, 11, 3)
    assert [k for k, s in seen if s == 'succeeded'] == ['extracting', 'checking', 'writing', 'report_checks', 'assembling']


def test_the_checked_medicines_are_handed_over_before_the_report_is_written():
    seen = []
    reference = reference_for(REF, REF.patients[CASE.patient_id], REF.doctors[CASE.doctor_id], REF.clinic)
    draft = process_typed('enc-1', CASE.transcript, CASE.patient_id, CASE.doctor_id, date(2026, 11, 3), FixtureClient(FIXTURES),
                          reference, frozenset(), lambda key, state: seen.append((key, state)),
                          on_checked=lambda checked: seen.append(('checked', checked)))
    keys = [k for k, _ in seen]
    assert keys.index('checked') < keys.index('writing')
    handed = seen[keys.index('checked')][1]
    # The suggestions get the medicines (same ids) the draft carries, in a copy of their own.
    assert [m.id for m in handed.medications] == [m.id for m in draft.checked.medications]
    assert handed is not draft.checked


def test_a_failed_stage_is_named_and_leaves_no_draft():
    class Broken:
        def generate(self, *args):
            raise RuntimeError('provider down')
    reference = reference_for(REF, REF.patients[CASE.patient_id], REF.doctors[CASE.doctor_id], REF.clinic)
    with pytest.raises(StageFailed) as failure:
        process_typed('enc-1', CASE.transcript, CASE.patient_id, CASE.doctor_id, date(2026, 11, 3), Broken(), reference,
                      frozenset(), lambda *a: None)
    assert failure.value.stage == 'extracting'


def test_an_empty_source_is_refused_rather_than_producing_an_empty_note():
    reference = reference_for(REF, REF.patients[CASE.patient_id], REF.doctors[CASE.doctor_id], REF.clinic)
    with pytest.raises(StageFailed, match='empty'):
        process_typed('enc-1', '   ', CASE.patient_id, CASE.doctor_id, date(2026, 11, 3), FixtureClient(FIXTURES),
                      reference, frozenset(), lambda *a: None)


def test_the_reference_carries_the_app_patient_not_the_seed_file():
    patient = {**REF.patients['pat-001'], 'name': 'Renamed In App'}
    reference = reference_for(REF, patient, REF.doctors['doc-001'], REF.clinic)
    assert reference.patients == {'pat-001': patient} and reference.products == REF.products
