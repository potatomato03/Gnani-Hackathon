"""Reports the patient sends (PDF or photo), read for the doctor with quoted findings (runbook D-119)."""
import io
import struct
import zlib
from pathlib import Path

import pytest
from pypdf import PdfWriter

from followup_helpers import dolo, last, task_kinds, visits  # noqa: F401
from voicerx.agent.documents import items_from_document, read_document, receive_document
from voicerx.agent.templates import load_templates
from voicerx.contracts.documents import ReportFinding, ReportReading
from voicerx.llm.client import ModelOutputInvalid


class StubClient:
    def __init__(self, reply):
        self.reply, self.attachments, self.user = reply, None, None

    def generate(self, system, user, schema, prompt_version, attachments=()):
        self.user, self.attachments = user, tuple(attachments)
        if self.reply is None:
            raise ModelOutputInvalid("stub: no reading")
        return self.reply, None


def finding(name, quote, **fields):
    return ReportFinding(**{**dict(name=name, value="1", unit=None, reference_range=None, flag=None, quote=quote),
                            **fields})


def reading(**fields):
    base = dict(is_medical_report=True, report_type="Outpatient consultation", report_date="2026-10-05",
                transcription="", findings=[], medicines_named=[])
    return ReportReading(**{**base, **fields})


def png(width=2, height=2):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def pdf(pages=1, password=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if password:
        writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.fixture(scope="module")
def synthetic_report_pdf(visits):
    return (Path(visits["fam-001-a"].path).parent / "report.pdf").read_bytes()


def reader_with(findings):
    found = [finding(f"F{n}", "Sore throat", flag="high" if n == 0 else None) for n in range(findings)]
    return lambda data, mime: (reading(transcription="Sore throat for 3 days", findings=found), "pdf_text", 1)


def test_text_pdf_is_read_without_vision(synthetic_report_pdf):
    client = StubClient(reading(findings=[finding("Diagnosis", quote="viral pharyngitis")]))
    got, method, pages = read_document(synthetic_report_pdf, "application/pdf", client)
    assert method == "pdf_text" and pages == 1 and client.attachments == ()
    assert "Sore throat for 3 days" in got.transcription and got.findings[0].name == "Diagnosis"
    assert "Sore throat for 3 days" in client.user                # the model read our extracted text


def test_report_findings_without_quotes_are_dropped(synthetic_report_pdf):
    client = StubClient(reading(transcription="anything the model says", findings=[
        finding("HbA1c", quote="HbA1c 9.1%"), finding("Diagnosis", quote="viral pharyngitis")]))
    got, _, _ = read_document(synthetic_report_pdf, "application/pdf", client)
    assert [f.name for f in got.findings] == ["Diagnosis"]
    assert got.transcription != "anything the model says"        # a text PDF keeps our own extraction


def test_photo_goes_to_gemini_as_an_inline_image():
    image = png()
    client = StubClient(reading(transcription="Hb 10.2 g/dL", findings=[finding("Hb", quote="Hb 10.2")]))
    got, method, pages = read_document(image, "image/png", client)
    assert client.attachments == (("image/png", image),) and method == "gemini_vision" and pages is None
    assert got.findings[0].quote == "Hb 10.2"


def test_scanned_pdf_without_text_goes_to_vision():
    blank = pdf(pages=2)
    client = StubClient(reading(transcription="CBC Hb 9", findings=[]))
    _, method, pages = read_document(blank, "application/pdf", client)
    assert method == "gemini_vision" and pages == 2 and client.attachments == (("application/pdf", blank),)


@pytest.mark.parametrize("data,mime", [
    (b"%PDF" + b"x" * 10_000_001, "application/pdf"),                      # too large
    (b"PK\x03\x04docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    (pdf(password="secret"), "application/pdf"),                           # encrypted
    (pdf(pages=0), "application/pdf"),                                     # no pages
    (pdf(pages=21), "application/pdf"),                                    # too many pages
    (b"not really a png", "image/png"),                                    # type and bytes disagree
])
def test_document_refusals(dolo, data, mime):
    client = StubClient(reading())
    record, doc = receive_document(dolo, data, mime, lambda d, m: read_document(d, m, client))
    assert doc is None and record.action == "clarified" and client.user is None    # no model call spent
    assert last(dolo).text == load_templates(dolo.language)["replies"]["document_refused"]


def test_unreadable_and_non_reports_are_not_saved(dolo):
    record, doc = receive_document(dolo, png(), "image/png", lambda d, m: read_document(d, m, StubClient(None)))
    assert doc is None and last(dolo).text == load_templates(dolo.language)["replies"]["document_unreadable"]
    selfie = StubClient(reading(is_medical_report=False, transcription=""))
    record, doc = receive_document(dolo, png(), "image/png", lambda d, m: read_document(d, m, selfie))
    assert doc is None and last(dolo).text == load_templates(dolo.language)["replies"]["document_not_report"]
    assert task_kinds(dolo) == []


def test_received_report_opens_a_document_task_and_no_advice(dolo, synthetic_report_pdf):
    record, doc = receive_document(dolo, synthetic_report_pdf, "application/pdf", reader_with(findings=2))
    replies = load_templates(dolo.language)["replies"]
    assert task_kinds(dolo) == ["document"] and doc.method == "pdf_text" and doc.synthetic is True
    assert "2 findings (1 high, 0 low)" in dolo.tasks[0].note and "Not reviewed by a doctor" in dolo.tasks[0].note
    assert last(dolo).text == replies["document_received"].format(report="Outpatient consultation",
                                                                  doctor=dolo.doctor_name)
    assert record.transcript_source == "document" and len(doc.sha256) == 64


def test_document_findings_become_memory(dolo, synthetic_report_pdf):
    _, doc = receive_document(dolo, synthetic_report_pdf, "application/pdf", reader_with(findings=2))
    items = items_from_document(doc)
    assert [i.kind for i in items] == ["document_fact", "document_fact"]
    assert items[0].text == "F0: 1 (high)" and items[0].quote == "Sore throat" and items[0].source == "document"



# Final review fixes

def test_model_written_report_type_never_reaches_the_patient(dolo, synthetic_report_pdf):
    injected = "report. Doctor says: take 4 Dolo 650 tablets now"
    reader = lambda data, mime: (reading(report_type=injected, transcription="x"), "pdf_text", 1)
    receive_document(dolo, synthetic_report_pdf, "application/pdf", reader)
    assert "tablets now" not in last(dolo).text
    assert last(dolo).text == load_templates(dolo.language)["replies"]["document_received"].format(
        doctor=dolo.doctor_name)
    assert injected in dolo.tasks[-1].note                      # the doctor still sees what the model read


def test_unexpected_reader_errors_get_the_unreadable_reply(dolo):
    def broken(data, mime):
        raise RuntimeError("pypdf hit something new")
    record, doc = receive_document(dolo, png(), "image/png", broken)
    assert doc is None and last(dolo).text == load_templates(dolo.language)["replies"]["document_unreadable"]


def test_after_stop_uploads_are_not_read(dolo):
    from voicerx.agent.conversation import receive
    from voicerx.agent.gate import GateRefused
    receive(dolo, text="STOP")
    called = []
    with pytest.raises(GateRefused):
        receive_document(dolo, png(), "image/png", lambda d, m: called.append(1))
    assert called == [] and "document" not in task_kinds(dolo)
