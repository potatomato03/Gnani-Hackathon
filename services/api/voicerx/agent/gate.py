"""Every message to a patient passes here. A refusal means nothing is sent."""
from ..contracts.followup import Message
from ..pipeline.assemble import content_hash
from .plan import IST, WINDOW
from .templates import answer_text, load_templates, medicine_rows, summary_text

CONSENT = 'followup_whatsapp'


class GateRefused(Exception):
    pass


def check_consent(consents):
    if CONSENT not in consents:
        raise GateRefused('no consent for follow-up messages')


def check_report(conv, approved):
    if approved.status != 'approved' or content_hash(approved) != approved.content_hash \
            or approved.content_hash != conv.report_hash:
        raise GateRefused('only the approved report this plan was built from may be used')


def check_schedule(touch):
    local = touch.due_at.astimezone(IST).time()
    if not WINDOW[0] <= local <= WINDOW[1]:
        raise GateRefused('scheduled messages go out only between 09:00 and 20:00 IST (outside sending hours)')


def check_reply(conv, approved, message: Message, red_flags):
    check_report(conv, approved)
    if message.kind != 'system':
        if conv.stopped:
            raise GateRefused('the patient sent STOP')
        check_consent(conv.consents)
    templates = load_templates(conv.language)
    urgent = templates['replies']['urgent'].format(doctor=conv.doctor_name)
    if red_flags and message.kind != 'urgent':
        raise GateRefused('a warning sign must get the urgent reply')
    if message.kind == 'urgent' and message.text != urgent:
        raise GateRefused('the urgent reply is fixed text and cannot be changed')
    if message.kind == 'answer':
        rows = medicine_rows(approved)
        if len(message.cites) != 1 or message.cites[0] not in rows \
                or message.text != answer_text(templates, rows[message.cites[0]]):
            raise GateRefused('an answer must be exactly the cited approved medicine row')
    if message.kind == 'summary':
        if message.cites != list(medicine_rows(approved)) or message.text != summary_text(
                templates, approved, summary_names(conv)):
            raise GateRefused('the summary must be exactly the approved medicine rows in fixed wording')
    return message


def summary_names(conv):
    from .templates import format_date
    return {'patient': conv.patient_name, 'doctor': conv.doctor_name, 'clinic': conv.clinic_name,
            'date': format_date(conv.visit_date)}
