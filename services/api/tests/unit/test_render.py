import pytest

from voicerx.exports.pdf.render import find_browser, html_to_pdf, render_html


def test_stalled_browser_is_killed_with_its_children_and_never_hangs(monkeypatch, tmp_path):
    # A stalled Edge kept its helpers' output pipes open, so a captured run waited forever (runbook C-41).
    import subprocess

    from voicerx.exports.pdf import render

    calls, killed = [], []

    class Stalled:
        pid = 4242

        def __init__(self, command, **options):
            calls.append(options)

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("msedge", timeout)

    monkeypatch.setattr(render.subprocess, "Popen", Stalled)
    monkeypatch.setattr(render, "_kill_tree", killed.append)
    with pytest.raises(RuntimeError, match="timed out"):
        html_to_pdf("<p>x</p>", tmp_path / "r.pdf")
    assert [p.pid for p in killed] == [4242]
    assert calls[0]["stdout"] is subprocess.DEVNULL and calls[0]["stderr"] is subprocess.DEVNULL


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


def test_approval_time_is_printed_in_indian_time(approved_report):
    # fam-008-a's signed PDF said "14:43 UTC" for an approval at 20:13 in India (runbook C-51).
    from datetime import datetime, timezone
    report = approved_report.model_copy(update={"approved_at": datetime(2026, 11, 2, 14, 43, tzinfo=timezone.utc)})
    assert "02-Nov-2026 20:13 IST" in render_html(report, None)
