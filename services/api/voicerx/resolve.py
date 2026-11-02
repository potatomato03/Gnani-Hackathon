"""Explicit doctor edits create a new version without rewriting source evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
from pydantic import TypeAdapter, ValidationError
from .contracts.medication import Dose, Duration, Food, Schedule
from .contracts.report import MODEL_SECTIONS, DraftReport, ReportLine, Resolution
from .pipeline.check_extraction import medicine_issues, MEDICINE_CODES
from .pipeline.assemble import DISPLAY_NAMES, content_hash, medicine_row, table_medicines, current_medicine_lines
from .reference import load_reference


class ResolutionRefused(Exception):
    pass


def resolve(draft, resolutions, reference):
    if draft.status != 'draft' or content_hash(draft) != draft.content_hash:
        raise ResolutionRefused('only an intact draft can be corrected')
    if not resolutions:
        raise ResolutionRefused('at least one correction is required')
    result = draft.model_copy(deep=True)
    products = {**reference.products, **result.products_used}
    frozen_reference = reference.model_copy(deep=True, update={'products': products})
    original_ids = {m.id for m in result.checked.medications}
    acknowledgements = set()
    touched = {}  # (section, index) -> 'edit_line' or 'remove_line', indexed as in the incoming draft
    added, dismissed = [], set()  # doctor-written lines are appended after removals; dismissed finding ids
    kept_ids = {item.id for item in result.checked.kept}
    seen = {r.id for r in result.resolutions}
    try:
        for correction in resolutions:
            if not correction.by.strip() or not correction.reason.strip():
                raise ResolutionRefused('author and reason are required')
            if correction.id in seen:
                raise ResolutionRefused('resolution ids must be unique')
            seen.add(correction.id)
            if correction.action == 'acknowledge':
                key = (correction.target, correction.value.get('code'))
                found = [i for i in result.issues if (i.target, i.code) == key]
                if not found or any(i.severity == 'block' for i in found):
                    raise ResolutionRefused('only an existing warning can be acknowledged')
                acknowledgements.add(key)
                continue
            if correction.action in ('edit_line', 'remove_line'):
                section, _, index = correction.target.partition(':')
                lines = result.sections.get(section)
                if lines is None or not index.isdigit() or int(index) >= len(lines):
                    raise ResolutionRefused('unknown report line')
                if correction.action == 'edit_line':
                    text = correction.value['text'].strip()
                    if not text:
                        raise ResolutionRefused('an edited line needs text')
                    lines[int(index)] = ReportLine(text=text, cites=lines[int(index)].cites)
                touched[(section, int(index))] = correction.action
                continue
            if correction.action == 'add_line':
                text, cites = correction.value['text'].strip(), list(correction.value['cites'])
                if correction.target not in MODEL_SECTIONS or not text or not set(cites) <= kept_ids:
                    raise ResolutionRefused('an added line needs a section, text and known findings')
                added.append((correction.target, ReportLine(text=text, cites=cites)))
                continue
            if correction.action == 'dismiss_item':
                if correction.target not in kept_ids:
                    raise ResolutionRefused('unknown finding')
                dismissed.add(correction.target)
                continue
            rx = next((m for m in result.checked.medications if m.id == correction.target), None)
            if rx is None:
                raise ResolutionRefused('unknown medication target')
            value = correction.value
            cleared = None
            if correction.action == 'choose_product':
                pid = value['product_id']
                if pid not in products:
                    raise ResolutionRefused('unknown product')
                rx.match, rx.product_id, rx.candidate_ids, rx.fuzzy = 'exact', pid, [pid], False
                result.products_used[pid] = products[pid].model_copy(deep=True)
            elif correction.action == 'set_dose':
                rx.dose = Dose.model_validate(value)
                cleared = 'dose_phrase'
            elif correction.action == 'set_timing':
                rx.schedule = TypeAdapter(Schedule).validate_python(value['schedule'])
                cleared = 'timing_phrase'
            elif correction.action == 'set_food':
                rx.food = TypeAdapter(Food).validate_python(value['food'])
                cleared = 'food_phrase'
            elif correction.action == 'set_duration':
                rx.duration = Duration.model_validate(value)
                cleared = 'duration_phrase'
            elif correction.action == 'remove_medicine':
                result.checked.medications.remove(rx)
            elif correction.action == 'confirm_order':
                rx.speaker_unclear = False
            if cleared:
                rx.unbound = [x for x in rx.unbound if x not in (cleared, cleared.removesuffix('_phrase'))]
                rx.unresolved = [x for x in rx.unresolved if x not in (cleared, cleared.removesuffix('_phrase'))]
    except (KeyError, ValidationError, TypeError) as error:
        raise ResolutionRefused('invalid correction value: ' + str(error)) from None
    allergies = result.record_snapshot['patient']['allergies']
    new_issues = medicine_issues(result.checked.medications, frozen_reference, allergies)
    def carry(issues):
        return [i for i in issues if not (i.code in MEDICINE_CODES and i.target in original_ids)
                and (i.target, i.code) not in acknowledgements]
    new_issues = [i for i in new_issues if (i.target, i.code) not in acknowledgements]
    if dismissed & {c for s, lines in result.sections.items() for i, line in enumerate(lines)
                     if touched.get((s, i)) != 'remove_line' for c in line.cites}:
        raise ResolutionRefused('a finding still used by a report line cannot be dismissed')
    # A finding the doctor restated in a new line, or dismissed, no longer carries the model's flags.
    restated = dismissed | {c for _, line in added for c in line.cites}
    result.issues = _apply_line_changes(result, carry(result.issues), touched, restated) + new_issues
    result.checked.issues = _apply_line_changes(result, carry(result.checked.issues), touched, restated) + new_issues
    for section, index in sorted((k for k, v in touched.items() if v == 'remove_line'), reverse=True):
        del result.sections[section][index]
    for section, line in added:
        result.sections[section].append(line)
    result.not_discussed = [DISPLAY_NAMES[s] for s in MODEL_SECTIONS if not result.sections.get(s)]
    result.medicines = [medicine_row(m, frozen_reference, result.header.visit_date) for m in table_medicines(result.checked)]
    result.current_medicines = current_medicine_lines(result.checked, frozen_reference)
    result.version += 1
    result.predecessor_hash = draft.content_hash
    result.resolutions.extend(r.model_copy(deep=True) for r in resolutions)
    result.content_hash = content_hash(result)
    return result


def _apply_line_changes(draft, issues, touched, restated=frozenset()):
    """Drop flags on lines the doctor edited or removed, on findings no untouched line still uses, and on
    findings the doctor restated or dismissed. Renumber the flags of lines that move up after a removal.
    Reads the draft's sections before removals and additions."""
    if not touched and not restated:
        return issues
    still_used = {c for s, lines in draft.sections.items() for i, line in enumerate(lines)
                  if (s, i) not in touched for c in line.cites}
    released = ({c for (s, i) in touched for c in draft.sections[s][i].cites} - still_used) | set(restated)
    kept = []
    for issue in issues:
        section, _, index = issue.target.partition(':')
        if index.isdigit():
            if (section, int(index)) in touched:
                continue
            shift = sum(1 for (s, i), action in touched.items()
                        if s == section and i < int(index) and action == 'remove_line')
            issue = issue.model_copy(update={'target': f'{section}:{int(index) - shift}'})
        elif issue.target in released:
            continue
        kept.append(issue)
    return kept


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--by', required=True)
    parser.add_argument('--reason', required=True)
    for action in ('choose', 'dose', 'timing', 'food', 'duration', 'remove', 'confirm', 'ack', 'edit', 'drop',
                   'add', 'dismiss'):
        parser.add_argument('--' + action, action='append', default=[])
    args = parser.parse_args()
    directory = args.directory.resolve()
    root = Path(__file__).resolve().parents[3]
    draft = DraftReport.model_validate_json((directory / 'draft_report.json').read_text(encoding='utf-8'))
    corrections = []
    names = {'choose': 'choose_product', 'dose': 'set_dose', 'timing': 'set_timing', 'food': 'set_food',
             'duration': 'set_duration', 'remove': 'remove_medicine', 'confirm': 'confirm_order', 'ack': 'acknowledge',
             'edit': 'edit_line', 'drop': 'remove_line', 'add': 'add_line', 'dismiss': 'dismiss_item'}
    for flag, action in names.items():
        for entry in getattr(args, flag):
            if flag == 'ack':
                code, target = entry.split('@', 1)
                value = {'code': code}
            elif flag == 'edit':
                target, text = entry.split('=', 1)
                value = {'text': text}
            elif flag == 'add':
                # --add "section=text|x1,x2": the cited finding ids follow the last "|".
                target, rest = entry.split('=', 1)
                text, _, cites = rest.rpartition('|') if '|' in rest else (rest, '', '')
                value = {'text': text, 'cites': [c for c in cites.split(',') if c]}
            elif flag in ('remove', 'confirm', 'drop', 'dismiss'):
                target, value = entry, {}
            else:
                target, text = entry.split('=', 1)
                if flag == 'choose': value = {'product_id': text}
                elif flag == 'food': value = {'food': text}
                elif flag == 'timing': value = {'schedule': json.loads(text)}
                else:
                    amount, unit = text.split(':', 1)
                    value = {'amount': amount, 'unit': unit} if flag == 'dose' else {'value': int(amount), 'unit': unit}
            corrections.append(Resolution(id=str(uuid4()), action=action, target=target, value=value,
                reason=args.reason, by=args.by, at=datetime.now(timezone.utc)))
    updated = resolve(draft, corrections, load_reference(root))
    # Refuse before writing anything, so a refused correction leaves no stray file behind.
    archive = directory / f'draft_report.v{draft.version}.json'
    if archive.exists():
        raise ResolutionRefused('previous version already archived; refusing overwrite')
    from .exports.pdf.render import render_html, html_to_pdf
    from .exports.patient_box import build_patient_box
    box = build_patient_box(updated, Path(__file__).parent / 'exports/templates/lang')
    pdf = html_to_pdf(render_html(updated, box), directory / 'report.next.pdf')
    (directory / 'draft_report.json').rename(archive)
    (directory / 'draft_report.json').write_text(updated.model_dump_json(indent=2), encoding='utf-8')
    pdf.replace(directory / 'report.pdf')
    print(f'Draft version {updated.version}; {sum(i.severity == "block" for i in updated.issues)} blocking issues')


if __name__ == '__main__':
    main()
