import pytest

from voicerx.exports.pdf.render import find_browser, html_to_pdf, render_html


def test_draft_shows_synthetic_banner_and_draft_watermark(draft_report):
    html = render_html(draft_report, None)
    assert "SYNTHETIC DATA" in html and "DRAFT, NOT APPROVED" in html


def test_approved_report_has_no_draft_watermark(approved_report):
    assert "DRAFT, NOT APPROVED" not in render_html(approved_report, None)


def test_medicine_label_and_detail_line_are_printed(draft_report):
    html = render_html(draft_report, None)
    assert "DOLO 650 TAB (PARACETAMOL) 650MG" in html
    assert "1 tablet, when needed, after food, for 3 days, start not stated" in html


def test_empty_sections_are_listed_as_not_discussed(draft_report):
    assert "Not discussed:" in render_html(draft_report, None)


def test_approved_footer_shows_version_fingerprint_and_approver(approved_report):
    html = render_html(approved_report, None)
    assert approved_report.content_hash[:12] in html and "Dr Test" in html and "Version 1" in html


def test_record_text_is_escaped(draft_report):
    header = draft_report.header.model_copy(update={"patient_name": "<script>alert(1)</script>"})
    html = render_html(draft_report.model_copy(update={"header": header}), None)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_pdf_prints_with_the_local_browser(draft_report, tmp_path):
    try:
        find_browser()
    except FileNotFoundError:
        pytest.skip("no headless browser on this machine")
    from pypdf import PdfReader
    pdf = html_to_pdf(render_html(draft_report, None), tmp_path / "report.pdf")
    reader = PdfReader(str(pdf))
    assert len(reader.pages) >= 1 and "SYNTHETIC DATA" in reader.pages[0].extract_text()
