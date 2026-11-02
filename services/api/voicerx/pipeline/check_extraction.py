"""Evidence integrity, mention boundaries, and deterministic medication checks."""
from hashlib import sha256
import re
import unicodedata
from ..contracts.extraction import CheckedExtraction, DroppedItem, ResolvedMedication
from ..contracts.issues import Issue
from ..contracts.medication import Taper, Start
from .match_medicine import match_medicine
from .schedule import parse_dose, parse_timing, parse_food, parse_duration, parse_start

NEGATION_WORDS = {'no', 'not', 'nil', 'without', 'denies', 'negative', 'never', 'नहीं', 'नही', 'न', 'ना', 'बिना',
                  'లేదు', 'లేవు', 'కాదు', 'இல்லை', 'இல்லாமல்'}
SIDE_WORDS = {'left': {'left', 'बायां', 'बाएँ', 'बाएं', 'बाईं', 'ఎడమ', 'இடது'},
              'right': {'right', 'दायां', 'दाएँ', 'दाएं', 'दाईं', 'కుడి', 'வலது'},
              'bilateral': {'bilateral', 'both', 'दोनों', 'రెండు', 'இரண்டு'}}
FIRST_PERSON = {'मैं', 'मुझे', 'मेरा', 'मेरी', 'i', 'my', 'me', 'నేను', 'నా', 'நான்', 'என்'}
ENDS = re.compile(r'[।?!\n]|\.(?=\s|$)')
PHRASES = ('dose_phrase', 'timing_phrase', 'food_phrase', 'duration_phrase', 'start_phrase', 'route_phrase')
MEDICINE_CODES = {'missing_quantity', 'ambiguous_product', 'fuzzy_product_match', 'unmatched_product',
                  'allergy_conflict', 'speaker_unclear', 'phrase_not_bound'} | {'unparsed_' + x for x in ('dose', 'timing', 'food', 'duration', 'start', 'route')}


def normalise(text):
    return ' '.join(unicodedata.normalize('NFC', text).casefold().split())


def has_word(text, words):
    text = normalise(text)
    # Python's \w excludes combining vowel marks in Indian scripts.
    # A cue must be bounded by punctuation/space, never by a vowel mark.
    def word_char(char):
        return unicodedata.category(char)[0] in 'LMN' or char == '_'
    for word in words:
        for match in re.finditer(re.escape(normalise(word)), text):
            if (match.start() == 0 or not word_char(text[match.start() - 1])) and (
                    match.end() == len(text) or not word_char(text[match.end()])):
                return True
    return False


def issue(code, target, severity='block', message=None):
    return Issue(code=code, severity=severity, target=target, message=message or code.replace('_', ' '))


def medicine_issues(medications, reference, allergies):
    issues = []
    for rx in medications:
        if rx.match != 'exact':
            code = 'fuzzy_product_match' if rx.fuzzy else 'ambiguous_product' if rx.match == 'ambiguous' else 'unmatched_product'
            issues.append(issue(code, rx.id))
        if rx.action in ('start', 'change', 'continue'):
            if rx.dose is None and not (isinstance(rx.schedule, Taper) and all(s.dose for s in rx.schedule.steps)):
                issues.append(issue('missing_quantity', rx.id))
            product = reference.products.get(rx.product_id)
            if product and allergies:
                ingredients = {c.ingredient.casefold() for c in product.components}
                for allergy in allergies:
                    forbidden = {allergy.casefold(), *[x.casefold() for x in reference.allergy_classes.get(allergy.casefold(), [])]}
                    if ingredients & forbidden:
                        issues.append(issue('allergy_conflict', rx.id, message='Listed allergy conflicts with product; class table is unreviewed'))
                        break
        if rx.speaker_unclear:
            issues.append(issue('speaker_unclear', rx.id))
        if rx.unbound:
            issues.append(issue('phrase_not_bound', rx.id, message='Unbound phrases: ' + ', '.join(rx.unbound)))
        for field in rx.unresolved:
            issues.append(issue('unparsed_' + field.removesuffix('_phrase'), rx.id, 'warn'))
    return issues


def _sentence(text, position):
    starts = [m.end() for m in ENDS.finditer(text[:position])]
    start = starts[-1] if starts else 0
    end = ENDS.search(text, position)
    return text[start:end.start() if end else len(text)]


def check_extraction(extraction, transcript, reference, patient_id, visit_date, current_ids=frozenset()):
    text = normalise(transcript)
    kept, dropped, medications, issues = [], [], [], []
    for item in extraction.items:
        quote = normalise(item.quote)
        if not quote or quote not in text:
            dropped.append(DroppedItem(item=item, reason='quote_not_found'))
            issues.append(issue('quote_not_found', item.id, 'warn'))
            continue
        if item.kind == 'exam' and item.said_by == 'patient':
            dropped.append(DroppedItem(item=item, reason='patient_speech'))
            issues.append(issue('patient_speech', item.id, 'warn'))
            continue
        if item.kind == 'exam' and (item.said_by == 'unclear' or has_word(_sentence(text, text.index(quote)), FIRST_PERSON)):
            issues.append(issue('speaker_unclear', item.id, 'warn'))
        negated = has_word(quote, NEGATION_WORDS)
        if (item.assertion == 'absent' and not negated) or (item.assertion == 'present' and negated and item.kind not in ('advice', 'plan', 'follow_up', 'order', 'referral') and not re.search(r'\bsorry\b', quote)):
            issues.append(issue('negation_mismatch', item.id))
        if item.laterality and not has_word(quote, SIDE_WORDS[item.laterality]):
            issues.append(issue('laterality_mismatch', item.id))
        kept.append(item)
    name_positions = [(m.start(), rx.id) for rx in extraction.medications
                      for m in re.finditer(re.escape(normalise(rx.name_quote)), text) if normalise(rx.name_quote)]
    for rx in extraction.medications:
        if rx.said_by == 'patient':
            issues.append(issue('patient_speech', rx.id, 'warn'))
            continue
        positions = [p for p, rid in name_positions if rid == rx.id]
        if not positions:
            issues.append(issue('quote_not_found', rx.id, 'warn'))
            continue
        values = {field: getattr(rx, field) for field in PHRASES}
        corrected = set()
        invalid_corrections = []
        for correction in extraction.corrections:
            if correction.target_id != rx.id:
                continue
            if correction.field not in PHRASES or not normalise(correction.old_quote) or normalise(correction.old_quote) not in text:
                invalid_corrections.append(correction.field)
                continue
            values[correction.field] = correction.new_quote
            corrected.add(correction.field)
        possibilities = []
        for pos in positions:
            following = [p for p, rid in name_positions if p > pos and rid != rx.id]
            next_name = min(following, default=len(text))
            end = ENDS.search(text, pos)
            stop = min(pos + 200, end.start() if end else len(text), next_name)
            bound = {field: (value is None or (bool(normalise(value)) and normalise(value) in text[pos:next_name if field in corrected else stop]))
                     for field, value in values.items()}
            possibilities.append((sum(bound.values()), pos, bound))
        _, pos, bound = max(possibilities, key=lambda entry: entry[0])
        unbound = [field for field in PHRASES if not bound[field]] + invalid_corrections
        clean = {field: value if bound[field] else None for field, value in values.items()}
        parsed = {'dose': parse_dose(clean['dose_phrase']), 'schedule': parse_timing(clean['timing_phrase']),
                  'food': parse_food(clean['food_phrase']), 'duration': parse_duration(clean['duration_phrase']),
                  'start': parse_start(clean['start_phrase'], visit_date), 'route': clean['route_phrase']}
        mapping = {'dose_phrase': 'dose', 'timing_phrase': 'schedule', 'food_phrase': 'food', 'duration_phrase': 'duration', 'start_phrase': 'start'}
        unresolved = [field for field, output in mapping.items() if clean[field] and parsed[output] is None]
        parsed['start'] = parsed['start'] or Start()
        match = match_medicine(rx.spoken_name, reference.products, current_ids)
        medications.append(ResolvedMedication(id=rx.id, action=rx.action, spoken_name=rx.spoken_name,
            **match.model_dump(), **parsed, unresolved=unresolved,
            quotes={'name_quote': rx.name_quote, **{field: value for field, value in values.items() if value is not None}},
            speaker_unclear=rx.said_by == 'unclear' or has_word(_sentence(text, pos), FIRST_PERSON), unbound=unbound))
    record = reference.patients[patient_id]
    allergies = record['allergies'] if record['allergy_status'] != 'unknown' else None
    issues += medicine_issues(medications, reference, allergies)
    return CheckedExtraction(transcript_sha256=sha256(transcript.encode('utf-8')).hexdigest(), kept=kept,
        dropped=dropped, medications=medications, corrections=extraction.corrections, issues=issues)
