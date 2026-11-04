"""Fixed follow-up wording per language, and the fixed medicine rows the agent may say."""
from functools import lru_cache
from pathlib import Path

import yaml

from ..exports.patient_box import build_patient_box
from ..pipeline.assemble import table_medicines

HERE = Path(__file__).parent / 'templates'
BOX_TEMPLATES = Path(__file__).parents[1] / 'exports/templates/lang'
SUPPORTED = {'hi-IN': 'hi', 'en-IN': 'en'}


@lru_cache(maxsize=None)
def load_templates(language):
    if language not in SUPPORTED:
        raise ValueError(f'no follow-up templates for {language} yet')
    return yaml.safe_load((HERE / (SUPPORTED[language] + '.yaml')).read_text(encoding='utf-8'))


def medicine_rows(approved, language=None):
    """Medicine id -> the exact row the patient may be told: the patient-language box row (fixed templates),
    or for English the approved medicine table row. Never model text. language: the conversation's language
    when the patient chose English for a visit in another language (D-116); None means the visit's own."""
    medicines = table_medicines(approved.checked)
    box = build_patient_box(approved, BOX_TEMPLATES, language=language)
    if box is not None:
        rows = box.rows
    else:
        rows = [row.label + ': ' + row.detail for row in approved.medicines]
    if len(rows) != len(medicines):
        raise ValueError('medicine rows do not line up with the approved medicines')
    return {rx.id: row for rx, row in zip(medicines, rows)}


def box_note(approved, language=None):
    box = build_patient_box(approved, BOX_TEMPLATES, language=language)
    return box.note if box is not None else ''


def format_date(day):
    return day.strftime('%d %b %Y').lstrip('0')


def answer_text(templates, row):
    reply = templates['replies']
    return '\n'.join([reply['answer_prefix'], row, reply['answer_suffix']])


def summary_text(templates, approved, names, language=None):
    """names: patient, doctor, clinic, date. The disclosure comes first (research R27)."""
    rows = medicine_rows(approved, language)
    parts = [templates['disclosure'].format(**names)]
    if rows:
        parts.append('\n'.join([templates['summary_intro'], *rows.values()]))
    note = box_note(approved, language)
    if note:
        parts.append(note)
    parts.append(templates['keywords_help'])
    return '\n\n'.join(parts)
