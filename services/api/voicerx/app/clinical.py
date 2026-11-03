"""The clinical engine, called as functions by the app (DESIGN.md section 8: never by shelling out to the CLI)."""
from ..pipeline.assemble import assemble_draft
from ..pipeline.check_extraction import check_extraction
from ..pipeline.check_report import check_report
from ..pipeline.extract import extract
from ..pipeline.run import active_after
from ..pipeline.write_report import write_report

STEPS = ['transcribing', 'extracting', 'checking', 'writing', 'report_checks', 'assembling', 'suggesting']


class StageFailed(Exception):
    def __init__(self, stage, message):
        self.stage = stage
        super().__init__(message)


def initial_steps(kind):
    """Typed input has nothing to transcribe."""
    return [{'key': key, 'state': 'skipped' if key == 'transcribing' and kind == 'typed' else 'pending'} for key in STEPS]


def reference_for(base, patient, doctor, clinic):
    """The catalog and rules as loaded, with the app's own patient, doctor and clinic records."""
    return base.model_copy(update={'patients': {patient['patient_id']: patient}, 'doctors': {doctor['doctor_id']: doctor},
                                   'clinic': clinic})


def current_ids(approved_reports):
    """Products still active after the patient's approved visits, oldest first."""
    active = frozenset()
    for report in approved_reports:
        active = active_after(report.checked, active)
    return active


def process_typed(case_id, transcript, patient_id, doctor_id, visit_date, client, reference, active_ids, on_step):
    if not transcript.strip():
        raise StageFailed('extracting', 'The source is empty; there is nothing to process.')
    stage = 'extracting'
    try:
        on_step(stage, 'running')
        extracted, _ = extract(client, transcript, reference)
        on_step(stage, 'succeeded')
        stage = 'checking'
        on_step(stage, 'running')
        checked = check_extraction(extracted, transcript, reference, patient_id, visit_date, active_ids)
        on_step(stage, 'succeeded')
        stage = 'writing'
        on_step(stage, 'running')
        fields, _ = write_report(client, checked)
        on_step(stage, 'succeeded')
        stage = 'report_checks'
        on_step(stage, 'running')
        issues = check_report(fields, checked, reference)
        on_step(stage, 'succeeded')
        stage = 'assembling'
        on_step(stage, 'running')
        draft = assemble_draft(case_id, patient_id, doctor_id, visit_date, fields, checked, issues, reference)
        on_step(stage, 'succeeded')
        return draft
    except StageFailed:
        raise
    except Exception as error:
        on_step(stage, 'failed')
        raise StageFailed(stage, f'{type(error).__name__}: {error}') from error
