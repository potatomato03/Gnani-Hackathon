from datetime import timedelta, timezone
import os
from pathlib import Path
import subprocess
import tempfile
from jinja2 import Environment, FileSystemLoader
from ...pipeline.assemble import DISPLAY_NAMES, REPORT_GROUPS

IST = timezone(timedelta(hours=5, minutes=30), 'IST')


def render_html(report, box):
    env = Environment(loader=FileSystemLoader(Path(__file__).parent), autoescape=True)
    # The clinic is in India: print approval times in IST whatever zone they were stored in (naive means UTC).
    env.filters['ist'] = lambda moment: (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(
        IST).strftime('%d-%b-%Y %H:%M IST')
    # Hex escapes keep arbitrary approver names safe inside a CSS string.
    from markupsafe import Markup
    # Lines run on as a paragraph, so each ends as a sentence.
    env.filters['sentence'] = lambda text: text.strip() + ('' if text.strip()[-1:] in '.!?' else '.')
    env.filters['css_string'] = lambda value: Markup('"' + ''.join('\\' + format(ord(c), 'x') + ' ' for c in str(value)) + '"')
    return env.get_template('report.html.j2').render(report=report, box=box, names=DISPLAY_NAMES,
                                                             groups=REPORT_GROUPS)


def find_browser():
    candidates = [os.environ.get('PDF_BROWSER'),
        str(Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'),
        str(Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Microsoft/Edge/Application/msedge.exe'),
        '/usr/bin/chromium', '/usr/bin/google-chrome']
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise FileNotFoundError('no headless browser; set PDF_BROWSER')


def html_to_pdf(html, out_pdf: Path):
    browser = find_browser()
    out_pdf = Path(out_pdf).resolve()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pdf-', dir=out_pdf.parent, ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        source, target = root / 'report.html', root / 'report.pdf'
        source.write_text(html, encoding='utf-8')
        command = [str(browser), '--headless=new', '--disable-gpu', '--no-pdf-header-footer',
                   '--no-first-run', '--no-default-browser-check', '--disable-extensions',
                   '--user-data-dir=' + str(root / 'profile'), '--print-to-pdf=' + str(target), source.as_uri()]
        # No captured pipes: Edge's helper processes can hold them open after a timeout, and a captured
        # run then waits forever. A stalled browser is killed with all its children.
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            returncode = process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            raise RuntimeError('headless browser timed out') from None
        if returncode or not target.exists() or not target.read_bytes().startswith(b'%PDF'):
            raise RuntimeError('headless browser failed to produce a PDF')
        target.replace(out_pdf)
    return out_pdf


def _kill_tree(process):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    else:
        process.kill()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
