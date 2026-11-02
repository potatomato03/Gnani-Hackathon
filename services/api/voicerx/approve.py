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
