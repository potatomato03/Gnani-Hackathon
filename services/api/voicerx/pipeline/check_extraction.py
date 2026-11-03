"""Evidence integrity, mention boundaries, and deterministic medication checks."""
from hashlib import sha256

from rapidfuzz import fuzz
import re
import unicodedata
from ..contracts.extraction import CheckedExtraction, DroppedItem, ResolvedMedication
from ..contracts.issues import Issue
from ..contracts.medication import AsNeeded, Frequency, Grid, Taper, Start
from .match_medicine import MatchResult, match_medicine
from .romanise import english_loanwords
from .schedule import parse_dose, parse_timing, parse_food, parse_duration, parse_meal, parse_start

NEGATION_WORDS = {'no', 'not', 'nil', 'without', 'denies', 'negative', 'never', 'नहीं', 'नही', 'न', 'ना', 'बिना',
                  'లేదు', 'లేవు', 'కాదు', 'இல்லை', 'இல்லாமல்', 'નથી', 'નહીં', 'નહિ', 'વગર'}
# A hedge in the quote means the doctor suspects, not states. Telugu and Tamil hedges are not yet listed.
HEDGE_WORDS = {'likely', 'probably', 'possibly', 'probable', 'suspected', 'suspect', 'provisional', 'seems',
               'looks like', 'could be', 'लग रहा', 'लग रही', 'लगता', 'लगती', 'शायद', 'संभवतः', 'કદાચ', 'લાગે છે'}
SIDE_WORDS = {'left': {'left', 'बायां', 'बाएँ', 'बाएं', 'बाईं', 'ఎడమ', 'இடது', 'ડાબો', 'ડાબા', 'ડાબી', 'ડાબે'},
              'right': {'right', 'दायां', 'दाएँ', 'दाएं', 'दाईं', 'కుడి', 'வலது', 'જમણો', 'જમણા', 'જમણી', 'જમણે'},
              'bilateral': {'bilateral', 'both', 'दोनों', 'రెండు', 'இரண்டு', 'બંને', 'બન્ને'}}
FIRST_PERSON = {'मैं', 'मुझे', 'मेरा', 'मेरी', 'i', 'my', 'me', 'నేను', 'నా', 'நான்', 'என்', 'હું', 'મને', 'મારો', 'મારી', 'મારું'}
# A doctor dictating says "I am recommending ..."; first person with a prescribing verb is the doctor, not a
# patient interrupting (runbook C-70).
PRESCRIBING = {'recommend', 'recommending', 'suggest', 'suggesting', 'prescribe', 'prescribing', 'advise', 'advising',
               'starting', 'giving', 'adding', 'i want you', 'लिख रहा', 'लिख रही', 'दे रहा', 'दे रही', 'આપું છું',
               'લખું છું', 'શરૂ કરો'}
NUKTA = '\u093c'  # the nukta dot, as in ज़
ENDS = re.compile(r'[।?!\n]|\.(?=\s|$)')
PHRASES = ('dose_phrase', 'timing_phrase', 'food_phrase', 'duration_phrase', 'start_phrase', 'route_phrase')
MEDICINE_CODES = {'missing_quantity', 'ambiguous_product', 'fuzzy_product_match', 'unmatched_product',
                  'allergy_conflict', 'speaker_unclear', 'phrase_not_bound'} | {'unparsed_' + x for x in ('dose', 'timing', 'food', 'duration', 'start', 'route')}


def normalise(text):
    # The nukta is written or left out at will ("ज़रूरत", "जरूरत"); it never tells two words apart here.
    return ' '.join(unicodedata.normalize('NFC', text).casefold().replace(NUKTA, '').split())


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
            issues.append(issue('phrase_not_bound', rx.id, message=said_away(rx)))
        for field in rx.unresolved:
            issues.append(issue('unparsed_' + field.removesuffix('_phrase'), rx.id, 'warn'))
    return issues


ROUTE_WORDS = {'orally', 'oral', 'by mouth', 'po'}
LINKING = {'से', 'है', 'हैं', 'का', 'की', 'के', 'लें', 'लेनी', 'लेना', 'लेने',
           'થી', 'છે', 'લેવી', 'લેવો', 'લેવા', 'લેવાની', 'જોઈએ', 'ની', 'નો', 'ના', 'માં',
           'is', 'are', 'was', 'will', 'be', 'should', 'for', 'dose', 'dosage', 'tablet', 'tablets', 'tab', 'capsule',
           'capsules', 'cap', 'syrup', 'sachet', 'inhaler', 'drops'}


LEAD_WORDS = 4
FIELD_WORDS = {'dose_phrase': 'dose', 'timing_phrase': 'timing', 'food_phrase': 'food', 'duration_phrase': 'duration',
               'start_phrase': 'start', 'route_phrase': 'route'}


def said_away(rx):
    """What was said away from this medicine, as heard: 'Said away from this medicine: duration “for three days”'."""
    said = [f'{FIELD_WORDS.get(f, f)} “{rx.quotes[f]}”' if rx.quotes.get(f) else FIELD_WORDS.get(f, f) for f in rx.unbound]
    return 'Said away from this medicine: ' + ', '.join(said)


def _other_spellings(medications, text, taken):
    """Later mentions of a medicine spelt another way (speech recognition wrote one brand two ways in one
    dictation, runbook C-71): words of five letters or more that closely match the first word of its quote and
    are not part of another medicine's name. Each counts as a mention of that medicine."""
    spans = [(s, e) for s, e, _ in taken]
    found = []
    for rx in medications:
        words = normalise(rx.name_quote).split()
        if not words or len(words[0]) < 5:
            continue
        for match in re.finditer(r'\S+', text):
            word = match.group().strip('.,;:!?…।')
            start = match.start()
            if (len(word) >= 5 and word != words[0] and fuzz.ratio(word, words[0]) >= 75
                    and not any(s <= start < e for s, e in spans)):
                found.append((start, start + len(word), rx.id))
                spans.append((start, start + len(word)))
    return found


def _patient_voice(sentence):
    return has_word(sentence, FIRST_PERSON) and not has_word(sentence, PRESCRIBING)


def _appears(phrase, window):
    """The phrase is in the window verbatim, or, for three words or more, its words appear there in order with at
    most two other words between them: "after breakfast and after dinner" in "one after breakfast and one after
    dinner". The model sometimes drops a repeated word when it copies."""
    if phrase in window:
        return True
    clean = lambda words: [w.strip('.,;:!?…।') for w in words]
    words, have = clean(phrase.split()), clean(window.split())
    if len(words) < 3:
        return False
    for start, word in enumerate(have):
        if word != words[0]:
            continue
        found, gap = 1, 0
        for other in have[start + 1:]:
            if found == len(words) or gap > 2:
                break
            if other == words[found]:
                found, gap = found + 1, 0
            else:
                gap += 1
        if found == len(words):
            return True
    return False


def _trim(phrase):
    return phrase.rstrip(' ।.?!,;') if phrase is not None else None


def _line_label(text, position):
    """The speaker label ("[doctor]", "[patient]") opening the transcript line at position, if any."""
    line = text[text.rfind('\n', 0, position) + 1:position].lstrip()
    match = re.match(r'\[(\w+)\]', line)
    return match[1] if match else None


def _sentence(text, position):
    starts = [m.end() for m in ENDS.finditer(text[:position])]
    start = starts[-1] if starts else 0
    end = ENDS.search(text, position)
    return text[start:end.start() if end else len(text)]


def check_extraction(extraction, transcript, reference, patient_id, visit_date, current_ids=frozenset()):
    text = normalise(transcript)
    # Keep a same-length copy with utterance boundaries for mention binding.
    bounded_text = re.sub(r'\s+', lambda m: '\n' if '\n' in m[0] or '\r' in m[0] else ' ',
                          unicodedata.normalize('NFC', transcript).casefold().replace(NUKTA, '')).strip()
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
        if item.kind == 'exam' and (item.said_by == 'unclear' or has_word(_sentence(bounded_text, text.index(quote)), FIRST_PERSON)):
            issues.append(issue('speaker_unclear', item.id, 'warn'))
        negated = has_word(quote, NEGATION_WORDS)
        if (item.assertion == 'absent' and not negated) or (item.assertion == 'present' and negated and item.kind not in ('advice', 'plan', 'follow_up', 'order', 'referral') and not re.search(r'\bsorry\b', quote)):
            issues.append(issue('negation_mismatch', item.id))
        if item.certainty == 'stated' and item.assertion == 'present' and has_word(quote, HEDGE_WORDS):
            issues.append(issue('certainty_mismatch', item.id))
        # The side may be said just outside a short quote, in its own sentence ("left knee में pain और instability
        # है"), as long as that sentence names no other side.
        sentence = _sentence(bounded_text, text.index(quote))
        side_in_sentence = item.laterality and has_word(sentence, SIDE_WORDS[item.laterality]) and not any(
            has_word(sentence, words) for side, words in SIDE_WORDS.items() if side != item.laterality)
        if item.laterality and not has_word(quote, SIDE_WORDS[item.laterality]) and not side_in_sentence:
            issues.append(issue('laterality_mismatch', item.id))
        kept.append(item)
    name_positions = [(m.start(), m.end(), rx.id) for rx in extraction.medications
                      for m in re.finditer(re.escape(normalise(rx.name_quote)), text) if normalise(rx.name_quote)]
    name_positions += _other_spellings(extraction.medications, text, name_positions)
    for rx in extraction.medications:
        positions = [p for p, _, rid in name_positions if rid == rx.id]
        # A medicine the model calls patient speech is dropped only on evidence: a [patient] line label, or,
        # with no label, a first-person sentence. Otherwise it is kept and blocked as unclear for the doctor
        # to confirm, never silently dropped.
        def patient_said(p):
            label = _line_label(bounded_text, p)
            return label == 'patient' if label else _patient_voice(_sentence(bounded_text, p))
        overruled = rx.said_by == 'patient' and not (positions and all(patient_said(p) for p in positions))
        if rx.said_by == 'patient' and not overruled:
            issues.append(issue('patient_speech', rx.id, 'warn'))
            continue
        if not positions:
            issues.append(issue('quote_not_found', rx.id, 'warn'))
            continue
        # A phrase copied with its closing mark ("…नहीं।") must still fit a mention that ends before the mark.
        values = {field: _trim(getattr(rx, field)) for field in PHRASES}
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
            # A medicine's words run from a few words before its name, so "one Pan D" keeps its dose, to the
            # sentence end or the next medicine named.
            # Only when its own sentence says nothing after the name ("the dosage for Pan D is... One after
            # breakfast") do they run on through the next sentence, and never across a line (another turn).
            others = [(s, e) for s, e, rid in name_positions if rid != rx.id]
            next_name = min((s for s, _ in others if s > pos), default=len(text))
            earlier_end = max((e for s, e in others if e <= pos), default=0)
            ends = [m.end() for m in ENDS.finditer(bounded_text[:pos])]
            # Only a short lead-in before the name counts ("take one Pan D"); further back, the words belong
            # to the medicine said before it.
            lead = [m.start() for m in re.finditer(r'\S+', text[:pos])][-LEAD_WORDS:]
            begin = max(earlier_end, ends[-1] if ends else 0, lead[0] if lead else 0)
            first_end = ENDS.search(bounded_text, pos)
            stop = first_end.start() if first_end else len(text)
            name_end = next(e for s, e, rid in name_positions if s == pos and rid == rx.id)
            after_name = {w.strip('.,;:!?…।') for w in text[name_end:stop].split()} - LINKING - {''}
            if first_end and first_end.group() != '\n' and not after_name:
                second_end = ENDS.search(bounded_text, first_end.end())
                stop = second_end.start() if second_end else len(text)
            stop = min(pos + 300, stop, next_name)
            bound = {field: (value is None or (bool(normalise(value)) and _appears(normalise(value), text[begin:next_name if field in corrected else stop])))
                     for field, value in values.items()}
            possibilities.append((sum(bound.values()), pos, bound))
        _, pos, bound = max(possibilities, key=lambda entry: entry[0])
        unbound = [field for field in PHRASES if not bound[field]] + invalid_corrections
        clean = {field: value if bound[field] else None for field, value in values.items()}
        # English said in Devanagari ("वन कैप्सूल") is read as English; the quotes keep what was written.
        read = {field: english_loanwords(value) if value else value for field, value in clean.items()}
        timing = (read['timing_phrase'] or '').strip(' .,।').lower()
        if timing in ROUTE_WORDS and not read['route_phrase']:
            # A route given as the timing ("ओरली", orally) is the route, not a time.
            read = {**read, 'route_phrase': timing, 'timing_phrase': None}
            clean = {**clean, 'timing_phrase': None}
        parsed = {'dose': parse_dose(read['dose_phrase']), 'schedule': parse_timing(read['timing_phrase']),
                  'food': parse_food(read['food_phrase']), 'duration': parse_duration(read['duration_phrase']),
                  'start': parse_start(read['start_phrase'], visit_date), 'route': read['route_phrase']}
        if parsed['duration'] is None and not read['duration_phrase'] and read['timing_phrase']:
            # "after breakfast and after dinner for three days": the duration came inside the timing phrase.
            parsed['duration'] = parse_duration(read['timing_phrase'])
        if isinstance(parsed['schedule'], Taper) and parsed['food'] is None and not read['food_phrase']:
            # A taper is quoted whole in its timing phrase, so its single food rule is said there too.
            parsed['food'] = parse_food(read['timing_phrase'])
        # "before breakfast" also says when: no timing, or "once a day" with one meal, becomes that slot.
        # A slot that contradicts the meal stays as said and is flagged; nothing is chosen between them.
        meal_conflict = False
        meal = parse_meal(read['food_phrase']) or parse_meal(read['timing_phrase'])
        if meal and not isinstance(parsed['schedule'], (AsNeeded, Taper)):
            slots = meal[1]
            schedule = parsed['schedule']
            if schedule is None or (isinstance(schedule, Frequency) and schedule.period == 'day'
                                    and schedule.times == len(slots)):
                parsed['schedule'] = Grid(**{s: '1' if s in slots else '0' for s in 'maen'})
            elif isinstance(schedule, Grid) and {s for s in 'maen' if float(getattr(schedule, s)) > 0} != slots:
                meal_conflict = True
            if parsed['food'] is None and not read['food_phrase']:
                # The meal said in the timing phrase is the food rule too ("after lunch and after dinner").
                parsed['food'] = meal[0]
        mapping = {'dose_phrase': 'dose', 'timing_phrase': 'schedule', 'food_phrase': 'food', 'duration_phrase': 'duration', 'start_phrase': 'start'}
        unresolved = [field for field, output in mapping.items() if clean[field] and parsed[output] is None]
        if meal_conflict and 'timing_phrase' not in unresolved:
            unresolved.append('timing_phrase')
        parsed['start'] = parsed['start'] or Start()
        match = match_medicine(rx.spoken_name, reference.products, current_ids)
        quoted_match = match_medicine(rx.name_quote, reference.products, current_ids)
        # A spoken name found verbatim in the transcript is as grounded as the quote, so its exact match stands.
        spoken_verbatim = bool(normalise(rx.spoken_name)) and normalise(rx.spoken_name) in text
        if match.match == 'exact' and not spoken_verbatim and (
                quoted_match.match != 'exact' or match.product_id != quoted_match.product_id):
            # Normalized spellings may differ, but the catalog identity must be grounded.
            match = quoted_match if quoted_match.match != 'exact' else MatchResult(
                match='unmatched', product_id=None, candidate_ids=[])
        elif (match.match == 'unmatched' and quoted_match.match == 'ambiguous'
              and normalise(rx.name_quote) in normalise(rx.spoken_name)):
            # A spoken name padded with the rest of its sentence defers to its verbatim quote, but only to
            # leave the doctor a choice: a short quote ("Amlong") must never pick one strength exactly.
            # A spoken name that contradicts the quote ("Dolo 500" against "Dolo six fifty") stays unmatched.
            match = quoted_match
        medications.append(ResolvedMedication(id=rx.id, action=rx.action, spoken_name=rx.spoken_name,
            **match.model_dump(), **parsed, unresolved=unresolved,
            quotes={'name_quote': rx.name_quote, **{field: value for field, value in values.items() if value is not None}},
            speaker_unclear=overruled or rx.said_by == 'unclear' or _patient_voice(_sentence(bounded_text, pos)), unbound=unbound))
    record = reference.patients[patient_id]
    allergies = record['allergies'] if record['allergy_status'] != 'unknown' else None
    issues += medicine_issues(medications, reference, allergies)
    return CheckedExtraction(transcript_sha256=sha256(transcript.encode('utf-8')).hexdigest(), kept=kept,
        dropped=dropped, medications=medications, corrections=extraction.corrections, issues=issues)
