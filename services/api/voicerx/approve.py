"""Approval binds an approver to the exact checked draft content."""
from .contracts.report import DraftReport, ApprovedReport
from .pipeline.assemble import content_hash


class ApprovalBlocked(Exception):
    def __init__(self, issues):
        self.issues = issues
        super().__init__('Approval blocked: ' + ', '.join(i.code for i in issues))


class HashMismatch(Exception):
    pass


def approve(draft: DraftReport, by, at):
    if draft.status != 'draft':
        raise ValueError('only a draft can be approved')
    if not by.strip():
        raise ValueError('approver name is required')
    blocking = [i for i in draft.issues if i.severity == 'block']
    if blocking:
        raise ApprovalBlocked(blocking)
    if content_hash(draft) != draft.content_hash:
        raise HashMismatch('draft content differs from its fingerprint')
    return ApprovedReport.model_validate({**draft.model_dump(), 'status': 'approved', 'approved_by': by.strip(), 'approved_at': at})


def main(argv=None):
    import argparse
    from datetime import date, datetime, timezone
    from pathlib import Path
    from .pipeline.run import save_json
    from .exports.pdf.render import render_html, html_to_pdf
    from .exports.patient_box import build_patient_box
    from .exports.fhir import build_bundles
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--by', required=True)
    parser.add_argument('--review-date', type=date.fromisoformat, default=None,
                        help='review date the doctor confirms (YYYY-MM-DD); follow-up reminds the patient before it')
    parser.add_argument('--followup', action='store_true',
                        help='start the patient follow-up now: the visit summary is sent (simulated channel)')
    args = parser.parse_args(argv)
    directory = args.directory.resolve()
    draft = DraftReport.model_validate_json((directory / 'draft_report.json').read_text(encoding='utf-8'))
    # Revalidate even when reusing an earlier approval's timestamp.
    approved = approve(draft, args.by, datetime.now(timezone.utc))
    approved_path = directory / 'approved_report.json'
    if approved_path.exists():
        previous = ApprovedReport.model_validate_json(approved_path.read_text(encoding='utf-8'))
        if previous.content_hash == draft.content_hash and previous.approved_by == args.by.strip():
            approved = previous
        else:
            # A different approval never overwrites a signed one; the earlier record and its outputs move aside.
            from .pipeline.run import SIGNED
            aside = directory / ('superseded-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            aside.mkdir()
            for path in directory.iterdir():
                if path.is_file() and SIGNED.fullmatch(path.name) and not path.name.startswith('draft_report'):
                    path.replace(aside / path.name)
    bundles = build_bundles(approved)
    box = build_patient_box(approved, Path(__file__).parent / 'exports/templates/lang')
    html_to_pdf(render_html(approved, box), directory / 'report_approved.pdf')
    for name, bundle in bundles.items():
        save_json(directory / ('fhir_' + name + '.json'), bundle)
    if 'prescription' not in bundles:
        (directory / 'fhir_prescription.json').unlink(missing_ok=True)
    save_json(approved_path, approved)
    save_json(directory / 'fhir_status.json', {'validation': 'not officially validated'})
    print(f'Approved version {approved.version}; fingerprint {approved.content_hash[:12]}')
    if args.review_date:
        from .agent.visits import write_followup_settings
        write_followup_settings(directory, args.review_date, args.by.strip(), approved.approved_at)
        print(f'Review date confirmed: {args.review_date.isoformat()}')
    if args.followup:
        from .agent.gate import GateRefused
        from .agent import visits
        try:
            conv = visits.start_followup(visits.load_visit(approved_path))
        except GateRefused as refusal:
            print(f'Follow-up not started: {refusal}')
        else:
            print(f'Follow-up started: conversation {conv.id} in {visits.STATE / "conversations"}')


if __name__ == '__main__':
    main()
