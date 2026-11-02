"""Approved visits the follow-up agent can run from, and starting a follow-up (runbook D-112).

Any approved_report.json under runs/ is a visit: the demo fixtures (runs/followup-demo/visits/) and every
real pipeline approval (runs/<run>/<case>/, written by voicerx.approve). Consent is read from the record
snapshot frozen with the draft. A review date is used only if the doctor confirmed it at approval, in a
followup.json beside the report; it is never read from model-written text (Q-25).
"""
import hashlib
import json
import os
from datetime import date
from pathlib import Path
from uuid import uuid4

from pydantic import Field, ValidationError

from ..contracts.followup import Conversation
from ..contracts.medication import Strict
from ..contracts.report import ApprovedReport
from ..pipeline.assemble import content_hash
from ..pipeline.run import REPO_ROOT

RUNS = REPO_ROOT / 'runs'
STATE = Path(os.environ.get('VOICERX_STATE_DIR', RUNS / 'followup-demo'))
SKIP_PARTS = ('pytest-tmp',)


class Visit(Strict):
    visit_id: str
    case_id: str
    source: str                     # 'demo' (built-in fixture) or 'run' (a real pipeline approval)
    path: str
    synthetic: bool = True
    clinic_id: str
    approved: ApprovedReport
    review_date: date | None = None
    consents: list[str] = Field(default_factory=list)


def visit_id_for(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = path.resolve().as_posix()
    return hashlib.sha256(relative.encode('utf-8')).hexdigest()[:12]


def load_visit(path: Path, root: Path = RUNS) -> Visit:
    """One approved report, checked: it must validate and match its own fingerprint."""
    path = Path(path)
    approved = ApprovedReport.model_validate_json(path.read_text(encoding='utf-8'))
    if content_hash(approved) != approved.content_hash:
        raise ValueError('approved report does not match its fingerprint')
    sidecar = path.parent / 'followup.json'
    settings = json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.exists() else {}
    review = date.fromisoformat(settings['review_date']) if settings.get('review_date') else None
    snapshot = approved.record_snapshot
    source = 'demo' if settings.get('source') == 'demo' else 'run'
    return Visit(visit_id=visit_id_for(path, root), case_id=approved.case_id, source=source, path=str(path),
                 clinic_id=snapshot['clinic']['clinic_id'], approved=approved, review_date=review,
                 consents=list(snapshot['patient'].get('consents', [])))


def find_approved_visits(root: Path = RUNS):
    """(visits, problems): every current approved report under root, and the ones that failed checks."""
    visits, problems = [], []
    if not Path(root).exists():
        return visits, problems
    for path in sorted(Path(root).rglob('approved_report.json')):
        parts = path.relative_to(root).parts
        if any(p.startswith('superseded-') or p in SKIP_PARTS for p in parts):
            continue
        try:
            visits.append(load_visit(path, root))
        except (ValidationError, ValueError, KeyError) as error:
            problems.append({'path': str(path), 'reason': str(error).splitlines()[0]})
    return visits, problems


def write_followup_settings(directory: Path, review_date: date | None, confirmed_by: str, at, source='run'):
    """followup.json beside an approved report: the doctor-confirmed review date, and whether the visit is a
    built-in demo fixture."""
    settings = {'source': source, 'review_date': review_date.isoformat() if review_date else None,
                'confirmed_by': confirmed_by, 'at': at.isoformat()}
    if review_date:
        settings['note'] = 'Review date confirmed by the doctor at approval (runbook Q-25).'
    (Path(directory) / 'followup.json').write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')


def stored_conversations(state_dir: Path | None = None):
    folder = Path(state_dir or STATE) / 'conversations'
    if not folder.exists():
        return []
    return [Conversation.model_validate_json(p.read_text(encoding='utf-8')) for p in sorted(folder.glob('*.json'))]


def start_followup(visit: Visit, state_dir: Path | None = None, restart=False) -> Conversation:
    """Start the follow-up for an approved visit, or return the one already running. Sends the summary."""
    from .conversation import attach, save, start
    state_dir = Path(state_dir or STATE)
    if not restart:
        for conv in stored_conversations(state_dir):
            if conv.visit_id == visit.visit_id and conv.report_hash == visit.approved.content_hash:
                return attach(conv, visit)
    conv = start(visit, uuid4().hex[:12])
    conv.visit_id = visit.visit_id
    save(conv, Path(state_dir) / 'conversations')
    return conv
