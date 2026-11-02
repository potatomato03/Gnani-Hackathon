"""Demo visits: synthetic cases run offline through the real pipeline, corrected and approved.

Each visit replays saved stage outputs (services/api/tests/fixtures/<case>/) through Check 1, Check 2 and
assembly, applies the doctor's audited corrections where the draft is blocked, and approves it. Nothing here
calls a model. Every record is synthetic.
"""
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from pydantic import Field

from ..approve import approve
from ..contracts.medication import Strict
from ..contracts.report import ApprovedReport, Resolution
from ..fixture_client import FixtureClient
from ..pipeline.run import REPO_ROOT, load_case_inputs, run_case, save_json
from ..reference import load_reference
from ..resolve import resolve
from .plan import IST

FIXTURES = REPO_ROOT / 'services/api/tests/fixtures'

# What the doctor does on the review screen before approving, for each demo visit.
DEMO_VISITS = {
    'fam-001-a': {'corrections': [], 'review_after_days': None},
    'fam-004-a': {
        # The script says "Currently taking Telma forty once daily" and later "Continue Telma forty" with no
        # dose, so Check 1 blocks missing_quantity. The doctor confirms the dose and timing.
        'corrections': [
            ('set_dose', 'rx1', {'amount': '1', 'unit': 'tablet'}),
            ('set_timing', 'rx1', {'schedule': {'type': 'frequency', 'times': 1, 'period': 'day'}}),
        ],
        'reason': 'Continuing the current dose: one tablet once daily, as the patient already takes it.',
        'review_after_days': None,
    },
    # "Review एक हफ़्ते बाद": the review date is confirmed by the doctor at approval, never parsed from text.
    'fam-010-a': {'corrections': [], 'review_after_days': 7},
}


class DemoVisit(Strict):
    case_id: str
    synthetic: bool = True
    clinic_id: str
    approved: ApprovedReport
    review_date: date | None = None
    consents: list[str] = Field(default_factory=list)


def build_visit(case_id, out_dir: Path, reference=None) -> DemoVisit:
    if case_id not in DEMO_VISITS:
        raise KeyError(case_id)
    setup = DEMO_VISITS[case_id]
    reference = reference or load_reference(REPO_ROOT)
    case = next(c for c in load_case_inputs(REPO_ROOT, 'typed') if c.case_id == case_id)
    result = run_case(case, FixtureClient(FIXTURES / case_id), reference, Path(out_dir) / case_id, frozenset())
    if result.status != 'draft':
        raise RuntimeError(f'{case_id} did not reach a draft: {result.stage}: {result.error}')
    draft = result.draft
    doctor = draft.header.doctor_name
    reviewed_at = datetime.combine(case.visit_date, time(10, 15), IST)
    if setup['corrections']:
        corrections = [Resolution(id=str(uuid5(NAMESPACE_URL, f'{case_id}/{i}')), action=action, target=target,
                                  value=value, reason=setup['reason'], by=doctor, at=reviewed_at)
                       for i, (action, target, value) in enumerate(setup['corrections'])]
        draft = resolve(draft, corrections, reference)
    approved = approve(draft, doctor, datetime.combine(case.visit_date, time(10, 30), IST))
    save_json(Path(out_dir) / case_id / 'approved_report.json', approved)
    days = setup['review_after_days']
    patient = reference.patients[case.patient_id]
    return DemoVisit(case_id=case_id, clinic_id=reference.clinic['clinic_id'], approved=approved,
                     review_date=case.visit_date + timedelta(days=days) if days else None,
                     consents=list(patient.get('consents', [])))
