"""Reports a patient sends (PDF or photo), read for the doctor (runbook D-119).

A PDF with a text layer is read with pypdf and the model only structures that text; a scanned PDF or a photo
goes to Gemini as an inline part. Every finding must quote the transcription or it is dropped. The patient gets
a fixed reply and the doctor a `document` task; the bot never explains results. The integrated journey stores
accepted originals in the clinic's private database; this reader itself does not write files.
"""
import hashlib
import io
import json
import logging
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ..contracts.documents import PatientDocument, ReportReading
from ..contracts.followup import Conversation, FollowUpRecord, MemoryItem, Message
from ..llm.client import ModelOutputInvalid, QuotaExhausted
from .conversation import STEP, _record, _reply, _task
from .gate import GateRefused
from .memory import patient_key_for_simulated
from .templates import load_templates
from .text import find, tokens

log = logging.getLogger('voicerx.documents')
ALLOWED = {'application/pdf', 'image/jpeg', 'image/png', 'image/webp'}
MAX_BYTES = 10_000_000
MAX_PAGES = 20
MIN_TEXT = 200          # fewer characters than this in the text layer: treat the PDF as scanned
PROMPT_VERSION = 'read-report-v1'
SYSTEM = (Path(__file__).parent / 'prompts' / 'read_report.md').read_text(encoding='utf-8')
MAGIC = {'application/pdf': lambda d: d.startswith(b'%PDF'), 'image/png': lambda d: d.startswith(b'\x89PNG'),
         'image/jpeg': lambda d: d.startswith(b'\xff\xd8\xff'),
         'image/webp': lambda d: d[:4] == b'RIFF' and d[8:12] == b'WEBP'}


class DocumentRefused(Exception):
    """Wrong type, too large, encrypted, or too many pages: refused before any model call."""


def _pdf_text(data):
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentRefused('the PDF is password-protected')
        pages = len(reader.pages)
        if not 1 <= pages <= MAX_PAGES:
            raise DocumentRefused(f'the PDF has {pages} pages; 1 to {MAX_PAGES} are accepted')
        return '\n'.join(page.extract_text() or '' for page in reader.pages), pages
    except (PdfReadError, ValueError, KeyError, TypeError) as error:
        raise DocumentRefused(f'the PDF could not be opened ({type(error).__name__})') from None


def _quoted(transcription, quote):
    return bool(tokens(quote)) and bool(find(tokens(transcription), quote))


def read_document(data: bytes, mime: str, client) -> tuple[ReportReading, str, int | None]:
    """(reading, method, pages). Raises DocumentRefused, or the client's QuotaExhausted / ModelOutputInvalid."""
    mime = (mime or '').split(';')[0].strip().lower()
    if mime not in ALLOWED or len(data) > MAX_BYTES or not MAGIC[mime](data):
        raise DocumentRefused('only a PDF or a JPG, PNG or WEBP photo under 10 MB is accepted')
    pages, text = None, ''
    if mime == 'application/pdf':
        text, pages = _pdf_text(data)
    if len(text.strip()) >= MIN_TEXT:
        method = 'pdf_text'
        reading, _ = client.generate(SYSTEM, json.dumps({'text': text}, ensure_ascii=False), ReportReading,
                                     PROMPT_VERSION)
        reading = reading.model_copy(update={'transcription': text})
    else:
        method = 'gemini_vision'
        reading, _ = client.generate(SYSTEM, json.dumps({'attached': mime}), ReportReading, PROMPT_VERSION,
                                     attachments=[(mime, data)])
    kept = [f for f in reading.findings if _quoted(reading.transcription, f.quote)]
    return reading.model_copy(update={'findings': kept}), method, pages


def _note(reading):
    flags = [f.flag for f in reading.findings]
    kind = reading.report_type or 'report'
    dated = f' dated {reading.report_date}' if reading.report_date else ''
    lines = [f'Patient sent a {kind}{dated}: {len(flags)} findings ({flags.count("high")} high, '
             f'{flags.count("low")} low). Not reviewed by a doctor.']
    for finding in reading.findings[:12]:
        lines.append(f'{finding.name}: {finding.value} {finding.unit or ""}'.strip() +
                     (f' [{finding.flag}]' if finding.flag else '') +
                     (f' (reference: {finding.reference_range})' if finding.reference_range else '') +
                     f' — source: «{finding.quote}»')
    return '\n'.join(lines)


def receive_document(conv: Conversation, data: bytes, mime: str, reader, original_saved=False) -> tuple[FollowUpRecord,
                                                                                  PatientDocument | None]:
    """A report from the patient. reader(data, mime) -> (reading, method, pages), e.g. read_document bound to a
    client; None when no model is configured. After STOP nothing is read (GateRefused, as for any message).
    The patient's reply is fixed text only: what the model read goes to the doctor's task, never to the patient."""
    if conv.stopped:
        raise GateRefused('the patient sent STOP')
    conv.clock = conv.clock + STEP
    replies, doctor = load_templates(conv.language)['replies'], conv.doctor_name
    label = 'Sent a PDF' if mime.startswith('application/pdf') else 'Sent a photo'
    conv.messages.append(Message(id=f'm{len(conv.messages) + 1}', sender='patient', text=label, at=conv.clock,
                                 touch_id=conv.awaiting.touch_id if conv.awaiting else None))
    try:
        if reader is None:
            raise ModelOutputInvalid('no model configured')
        reading, method, pages = reader(data, mime)
    except DocumentRefused:
        reply, reading = 'document_refused', None
    except (QuotaExhausted, ModelOutputInvalid):
        reply, reading = 'document_unreadable', None
    except Exception as error:   # a reader failure the model client didn't map: still a fixed reply
        log.warning('report not read: %s', type(error).__name__)
        reply, reading = 'document_unreadable', None
    else:
        reply = 'document_received' if reading.is_medical_report else 'document_not_report'
    if reply != 'document_received':
        if original_saved and reply == 'document_unreadable':
            reply = 'document_saved_review'
        record = _record(conv, label, 'document', 'clarified', [])
        _reply(conv, record, 'text', replies[reply])
        return record, None
    record = _record(conv, f'{label}: {reading.report_type or "report"}', 'document', 'recorded', [])
    doc = PatientDocument(id=f'{conv.id}-d{len(conv.records)}', patient_key=conv.patient_key or
                          patient_key_for_simulated(conv), visit_ref=conv.case_id, mime=mime.split(';')[0],
                          sha256=hashlib.sha256(data).hexdigest(), pages=pages, method=method, reading=reading,
                          received_at=conv.clock)
    _task(conv, 'document', record, _note(reading))
    _reply(conv, record, 'text', replies['document_received'].format(doctor=doctor))
    return record, doc


def items_from_document(doc: PatientDocument) -> list[MemoryItem]:
    out = []
    for n, f in enumerate(doc.reading.findings, 1):
        value = ' '.join(filter(None, [f.value, f.unit]))
        out.append(MemoryItem(id=f'{doc.id}-f{n}', patient_key=doc.patient_key, visit_ref=doc.visit_ref,
                              kind='document_fact', text=f'{f.name}: {value}' + (f' ({f.flag})' if f.flag else ''),
                              quote=f.quote, source='document', source_ref=doc.id, at=doc.received_at))
    return out
