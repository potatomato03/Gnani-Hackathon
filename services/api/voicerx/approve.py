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


def main():
    import argparse
    from datetime import datetime, timezone
    from pathlib import Path
    from .pipeline.run import save_json
    from .exports.pdf.render import render_html, html_to_pdf
    from .exports.patient_box import build_patient_box
    from .exports.fhir import build_bundles
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--by', required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    draft = DraftReport.model_validate_json((directory / 'draft_report.json').read_text(encoding='utf-8'))
    # Revalidate even when reusing an earlier approval's timestamp.
    approved = approve(draft, args.by, datetime.now(timezone.utc))
    approved_path = directory / 'approved_report.json'
    if approved_path.exists():
        previous = ApprovedReport.model_validate_json(approved_path.read_text(encoding='utf-8'))
        if previous.content_hash == draft.content_hash and previous.approved_by == args.by.strip():
            approved = previous
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


if __name__ == '__main__':
    main()
