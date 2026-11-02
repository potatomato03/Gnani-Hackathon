import os
from pathlib import Path
import subprocess
import tempfile
from jinja2 import Environment, FileSystemLoader
from ...pipeline.assemble import DISPLAY_NAMES


def render_html(report, box):
    env = Environment(loader=FileSystemLoader(Path(__file__).parent), autoescape=True)
    # Hex escapes keep arbitrary approver names safe inside a CSS string.
    from markupsafe import Markup
    env.filters['css_string'] = lambda value: Markup('"' + ''.join('\\' + format(ord(c), 'x') + ' ' for c in str(value)) + '"')
    return env.get_template('report.html.j2').render(report=report, box=box, names=DISPLAY_NAMES)


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
        result = subprocess.run(command, capture_output=True, timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode or not target.exists() or not target.read_bytes().startswith(b'%PDF'):
            raise RuntimeError('headless browser failed to produce a PDF')
        target.replace(out_pdf)
    return out_pdf
