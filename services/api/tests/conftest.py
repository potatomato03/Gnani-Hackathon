from pathlib import Path
import sys
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / 'services/api'))

import pytest
from datetime import date


def resolved_medicine(**changes):
    from voicerx.contracts.extraction import ResolvedMedication
    from voicerx.contracts.medication import AsNeeded, Dose, Duration, Start
    base = dict(id='rx1', action='start', spoken_name='Dolo six fifty', match='exact', product_id='p-dolo-650',
        candidate_ids=['p-dolo-650'], dose=Dose(amount='1', unit='tablet'), schedule=AsNeeded(),
        food='after_food', duration=Duration(value=3, unit='day'), start=Start(), route=None, unresolved=[], quotes={})
    return ResolvedMedication(**{**base, **changes})


def make_draft(medications, patient_id='pat-001'):
    from voicerx.contracts.extraction import CheckedExtraction, ExtractedItem
    from voicerx.contracts.report import ReportFields, ReportLine
    from voicerx.reference import load_reference
    from voicerx.pipeline.check_extraction import medicine_issues
    from voicerx.pipeline.assemble import assemble_draft
    reference = load_reference(REPO_ROOT)
    base = dict(kind='symptom', certainty='stated', temporality='current', laterality=None, subject='patient', said_by='doctor')
    items = [ExtractedItem(**base, id='x1', term='sore throat for three days', quote='तीन दिन से गले में दर्द', assertion='present'),
             ExtractedItem(**base, id='x2', term='fever', quote='बुखार नहीं है', assertion='absent')]
    checked = CheckedExtraction(transcript_sha256='fixture', kept=items, dropped=[], medications=medications, corrections=[],
        issues=medicine_issues(medications, reference, reference.patients[patient_id]['allergies']))
    fields = ReportFields(chief_complaints=[ReportLine(text='Sore throat for 3 days', cites=['x1'])],
                          history_present_illness=[ReportLine(text='No fever', cites=['x2'])])
    return assemble_draft('fixture-1', patient_id, 'doc-001', date(2026,10,5), fields, checked, [], reference)


@pytest.fixture
def draft_report():
    return make_draft([resolved_medicine()])


@pytest.fixture
def approved_report(draft_report):
    from datetime import datetime
    from voicerx.approve import approve
    return approve(draft_report, 'Dr Test', datetime(2026, 10, 5, 12, 0))


class FixtureClient:
    def __init__(self, directory, mutate=None):
        self.directory, self.mutate = directory, mutate

    def generate(self, system, user, schema, prompt_version):
        import json
        from voicerx.llm.client import CallMeta
        name = 'extraction' if prompt_version.startswith('extract') else 'report_fields'
        data = json.loads((self.directory / (name + '.json')).read_text(encoding='utf-8'))
        if self.mutate:
            data = self.mutate(prompt_version, data)
        return schema.model_validate(data), CallMeta(provider='fixture', model='fixture',
            prompt_version=prompt_version, cache_key=name, cached=True, key_index=0, attempts=0)
