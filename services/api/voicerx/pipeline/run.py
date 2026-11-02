"""Run synthetic transcripts through both checked stages, preserving each artifact."""
import argparse
from dataclasses import dataclass, asdict
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
import yaml
from ..contracts.issues import Issue
from ..contracts.report import DraftReport
from ..reference import load_reference
from ..llm.client import build_client
from ..exports.pdf.render import find_browser, html_to_pdf, render_html
from ..exports.patient_box import build_patient_box
from .extract import extract
from .check_extraction import check_extraction
from .write_report import write_report
from .check_report import check_report
from .assemble import assemble_draft

REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass
class CaseInput:
    case_id: str
    family_id: str
    encounter_index: int
    transcript: str | None
    patient_id: str
    doctor_id: str
    visit_date: date
    language: str


@dataclass
class RunResult:
    status: str
    stage: str | None
    error: str | None
    draft: DraftReport | None
    active_ids: frozenset[str] = frozenset()


def load_case_inputs(repo_root: Path, source):
    if source not in ('typed', 'whisper'):
        raise ValueError('source must be typed or whisper')
    cases = []
    for path in sorted((repo_root / 'data/eval/cases').glob('*.yaml')):
        # Deliberately do not instantiate the gold Family models or access expected fields.
        family = yaml.safe_load(path.read_text(encoding='utf-8'))
        for index, encounter in enumerate(family['encounters']):
            for variant in encounter['variants']:
                case_id = variant['variant_id']
                if source == 'typed':
                    transcript = '\n'.join(u['text'] for u in variant['utterances'])
                else:
                    transcript_path = repo_root / 'data/eval/results/whisper' / (case_id + '.txt')
                    transcript = transcript_path.read_text(encoding='utf-8').strip() if transcript_path.exists() else None
                visit_date = encounter['date']
                if isinstance(visit_date, str):
                    visit_date = date.fromisoformat(visit_date)
                cases.append(CaseInput(case_id, family['family_id'], index, transcript, family['patient_id'],
                                      encounter['doctor_id'], visit_date, family['language']))
    return sorted(cases, key=lambda c: (c.family_id, c.encounter_index, c.case_id))


def active_after(checked, before):
    active = set(before)
    for rx in checked.medications:
        if rx.match != 'exact' or not rx.product_id or rx.speaker_unclear or rx.unbound:
            continue
        if rx.action == 'stop':
            active.discard(rx.product_id)
        elif rx.action in ('start', 'continue', 'change'):
            active.add(rx.product_id)
    return frozenset(active)


def current_ids_for(case, finished, cases):
    previous = [c for c in cases if c.family_id == case.family_id and c.encounter_index < case.encounter_index]
    if not previous:
        return frozenset(), []
    prior_index = max(c.encounter_index for c in previous)
    previous = [c for c in previous if c.encounter_index == prior_index]
    if len(previous) != 1:
        return frozenset(), []
    result = finished.get(previous[0].case_id)
    if result is None or result.status != 'draft':
        return frozenset(), [Issue(code='previous_encounter_incomplete', severity='warn', target=case.case_id,
                                  message='Previous encounter is incomplete; medicine history is unavailable')]
    return result.active_ids, []


def save_json(path, value):
    path = Path(path)
    payload = value.model_dump(mode='json') if hasattr(value, 'model_dump') else value
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def run_case(case, client, reference, out_dir, current_ids, history_issues=()):
    out_dir = Path(out_dir)
    if out_dir.is_symlink():
        raise ValueError('run output directory must not be a symlink')
    out_dir = out_dir.resolve()
    if out_dir == REPO_ROOT or out_dir in REPO_ROOT.parents or out_dir == REPO_ROOT / 'runs':
        raise ValueError('a dedicated case output directory is required')
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in out_dir.iterdir():
        if path.is_symlink():
            raise ValueError('run output contains a symlink')
        if path.is_file():
            if path.resolve().parent != out_dir:
                raise ValueError('output escaped case directory')
            path.unlink()
    if case.transcript is None:
        save_json(out_dir / 'status.json', {'status': 'missing_input'})
        return RunResult('missing_input', None, None, None)
    (out_dir / 'transcript.txt').write_text(case.transcript, encoding='utf-8')
    metadata = {'transcript_sha256': sha256(case.transcript.encode('utf-8')).hexdigest(), 'stages': {}}
    stage = 'extract'
    try:
        extracted, meta = extract(client, case.transcript, reference)
        save_json(out_dir / 'extraction.json', extracted)
        metadata['stages']['extract'] = asdict(meta)
        save_json(out_dir / 'meta.json', metadata)
        stage = 'check_extraction'
        checked = check_extraction(extracted, case.transcript, reference, case.patient_id, case.visit_date, current_ids)
        save_json(out_dir / 'checked_extraction.json', checked)
        stage = 'write_report'
        fields, meta = write_report(client, checked)
        save_json(out_dir / 'report_fields.json', fields)
        metadata['stages']['write_report'] = asdict(meta)
        save_json(out_dir / 'meta.json', metadata)
        stage = 'check_report'
        issues = check_report(fields, checked, reference) + list(history_issues)
        draft = assemble_draft(case.case_id, case.patient_id, case.doctor_id, case.visit_date, fields, checked, issues, reference)
        stage = 'render_pdf'
        try:
            find_browser()
        except FileNotFoundError:
            metadata['pdf'] = 'no browser'
        else:
            box = build_patient_box(draft, Path(__file__).parents[1] / 'exports/templates/lang')
            html_to_pdf(render_html(draft, box), out_dir / 'report.pdf')
            metadata['pdf'] = 'ready'
        save_json(out_dir / 'draft_report.json', draft)
        save_json(out_dir / 'meta.json', metadata)
        active = active_after(checked, current_ids)
        save_json(out_dir / 'status.json', {'status': 'draft', 'active_ids': sorted(active)})
        return RunResult('draft', None, None, draft, active)
    except Exception as error:
        for name in ('draft_report.json', 'report.pdf'):
            (out_dir / name).unlink(missing_ok=True)
        message = f'{type(error).__name__}: {error}'
        save_json(out_dir / 'status.json', {'status': 'incomplete', 'stage': stage, 'error': message})
        save_json(out_dir / 'meta.json', metadata)
        return RunResult('incomplete', stage, message, None)


def run_cases(cases, client, reference, run_dir, workers=1, selected=None):
    from concurrent.futures import ThreadPoolExecutor
    if not 1 <= workers <= 4:
        raise ValueError('workers must be between 1 and 4')
    families = {}
    for case in cases:
        if selected and case.case_id not in selected:
            continue
        families.setdefault(case.family_id, []).append(case)

    def run_family(family_cases):
        finished = {}
        for case in sorted(family_cases, key=lambda c: (c.encounter_index, c.case_id)):
            ids, history = current_ids_for(case, finished, cases)
            print(case.case_id + ': running', flush=True)
            result = run_case(case, client, reference, Path(run_dir) / case.case_id, ids, tuple(history))
            finished[case.case_id] = result
            blocks = sum(i.severity == 'block' for i in result.draft.issues) if result.draft else 0
            print(f'{case.case_id}: {result.status}; {blocks} blocks' + (f'; {result.stage}: {result.error}' if result.error else ''), flush=True)
        return finished

    if workers == 1:
        return {key: value for family in families.values() for key, value in run_family(family).items()}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return {key: value for finished in pool.map(run_family, families.values()) for key, value in finished.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, choices=['typed', 'whisper'])
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--cases', nargs='+')
    parser.add_argument('--provider', choices=['gemini', 'ollama'])
    parser.add_argument('--workers', type=int, default=1, choices=range(1, 5),
                        help='independent families in flight; local GPU calls remain serialized')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('run-id must be a simple directory name')
    cases = load_case_inputs(REPO_ROOT, args.source)
    known = {c.case_id for c in cases}
    if args.cases and not set(args.cases) <= known:
        parser.error('unknown case id')
    reference = load_reference(REPO_ROOT)
    client = build_client(REPO_ROOT / '.env', REPO_ROOT / 'runs/cache', only=args.provider)
    run_cases(cases, client, reference, REPO_ROOT / 'runs' / args.run_id, args.workers, args.cases)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
