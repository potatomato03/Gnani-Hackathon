"""Fixed, visibly unreviewed language templates; no model translation."""
from dataclasses import dataclass
from pathlib import Path
import yaml
from ..contracts.medication import Grid, Frequency, AsNeeded, Taper
from ..pipeline.assemble import table_medicines


@dataclass
class PatientBox:
    language: str
    title: str
    rows: list[str]
    note: str
    reviewed: bool
    official_note: str = ''


def build_patient_box(report, templates_dir: Path):
    if report.language_pref == 'en-IN':
        return None
    language = report.language_pref.split('-')[0]
    if language not in ('hi', 'te', 'ta'):
        raise ValueError('no reviewed or draft template for this language')
    template = yaml.safe_load((templates_dir / (language + '.yaml')).read_text(encoding='utf-8'))
    ask = template['ask_doctor']
    def dose(value):
        return value.amount + ' ' + template['units'].get(value.unit, ask) if value else ask
    def duration(value):
        return template['duration'][value.unit].format(n=value.value) if value else ask
    def timing(value):
        if isinstance(value, Grid):
            return ', '.join(template['slots'][s] for s in 'maen' if float(getattr(value, s)) > 0) or ask
        if isinstance(value, Frequency) and value.period == 'day':
            return template['frequency'].format(n=value.times)
        if isinstance(value, AsNeeded):
            return template['as_needed_max'].format(n=value.max_per_day) if value.max_per_day else template['as_needed']
        return ask
    rows = []
    for rx in table_medicines(report.checked):
        if rx.match != 'exact' or rx.product_id not in report.products_used:
            rows.append(ask)
            continue
        name = report.products_used[rx.product_id].brand.upper()
        food = template['food'].get(rx.food, ask)
        if isinstance(rx.schedule, Taper):
            steps = template['then'].join(template['taper_step'].format(dose=dose(s.dose), when=timing(s.when),
                duration=duration(s.duration)) for s in rx.schedule.steps)
            rows.append(template['taper_row'].format(name=name, steps=steps, food=food))
        else:
            rows.append(template['row'].format(name=name, dose=dose(rx.dose), when=timing(rx.schedule), food=food,
                                               duration=duration(rx.duration)))
    reviewed = bool(template.get('reviewed_by'))
    return PatientBox(language=report.language_pref, title=template['title'], rows=rows,
                      note='' if reviewed else template['unreviewed_note'], reviewed=reviewed,
                      official_note=template['official_note'])
