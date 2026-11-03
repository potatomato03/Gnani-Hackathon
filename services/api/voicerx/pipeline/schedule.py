"""Parse only explicit instructions; unknown or ambiguous text stays unresolved."""
from datetime import date, timedelta
import re
from ..contracts.medication import Dose, Duration, Frequency, Grid, AsNeeded, Taper, TaperStep, Start
from .numbers import words_to_digits

UNIT_WORDS = {'tablet': 'tablet', 'tablets': 'tablet', 'tab': 'tablet', 'tabs': 'tablet', 'गोली': 'tablet',
              'गोलियाँ': 'tablet', 'टैबलेट': 'tablet', 'capsule': 'capsule', 'capsules': 'capsule',
              'puff': 'puff', 'puffs': 'puff', 'चम्मच': 'teaspoon', 'teaspoon': 'teaspoon', 'ml': 'ml', 'mg': 'mg'}
DURATIONS = {'day': 'day', 'days': 'day', 'दिन': 'day', 'రోజులు': 'day', 'రోజుల': 'day', 'நாட்கள்': 'day',
             'week': 'week', 'weeks': 'week', 'हफ़्ते': 'week', 'हफ्ते': 'week', 'हफ़्तों': 'week', 'வாரம்': 'week',
             'month': 'month', 'months': 'month', 'महीने': 'month', 'महीना': 'month', 'महीनों': 'month'}
SLOTS = {'m': ('morning', 'सुबह', 'subah', 'ఉదయం', 'காலையில்', 'காலை'),
         'a': ('afternoon', 'दोपहर', 'మధ్యాహ్నం', 'மதியம்'),
         'e': ('evening', 'शाम', 'సాయంత్రం', 'மாலை'),
         'n': ('night', 'bedtime', 'रात', 'raat', 'రాత్రి', 'இரவு')}
FOODS = {'after_food': ('after food', 'after meals', 'खाने के बाद', 'భోజనం తర్వాత', 'சாப்பாட்டுக்கு பின்'),
         'before_food': ('before food', 'before meals', 'खाने से पहले', 'భోజనం ముందు', 'சாப்பாட்டுக்கு முன்'),
         'with_food': ('with food', 'with meals', 'खाने के साथ'),
         'empty_stomach': ('empty stomach', 'खाली पेट')}
# A meal names a slot, and the word beside it the food rule (spec 2026-11-03, part A). English puts the
# relation first ("before breakfast", "post-lunch"); Hindi puts it after ("नाश्ते से पहले", "breakfast के बाद").
MEALS = {'m': ('breakfast', 'नाश्ते', 'नाश्ता'), 'a': ('lunch', 'दोपहर के खाने', 'दोपहर का खाना'),
         'n': ('dinner', 'supper', 'रात के खाने', 'रात का खाना')}
RELATION_BEFORE = re.compile(r'(before|after|with|pre|post)[\s-]*$')
RELATION_AFTER = re.compile(r'^\s*(से पहले|के बाद|के साथ)')
RELATIONS = {'before': 'before_food', 'pre': 'before_food', 'से पहले': 'before_food', 'after': 'after_food',
             'post': 'after_food', 'के बाद': 'after_food', 'with': 'with_food', 'के साथ': 'with_food'}


def _text(phrase):
    text = words_to_digits(phrase or '')
    # Discard explicitly superseded wording, never choose between alternatives.
    if 'sorry' in text:
        text = text.split('sorry', 1)[1]
    # Only a trailing ", not 5" or a standalone ", नहीं," marks a correction. "not more than 4" and
    # "से ज़्यादा नहीं, खाने के बाद" are part of the instruction and must survive.
    text = re.sub(r',?\s+not\s+\d+(?:\.\d+)?\b[^,]*$', '', text)
    parts = re.split(r'(?:^|,)\s*नहीं\s*,', text)
    return parts[-1] if len(parts) > 1 else text


def _values(text, vocabulary):
    units = '|'.join(re.escape(w) for w in sorted(vocabulary, key=len, reverse=True))
    return [(n, vocabulary[u]) for n, u in re.findall(r'(?<![\d.])(\d+(?:\.\d+)?)\s*(' + units + r')(?!\w)', text)]


def parse_dose(phrase):
    text = _text(phrase)
    values = set(_values(text, UNIT_WORDS))
    if len(values) != 1:
        return None
    amount, unit = next(iter(values))
    return Dose(amount=amount, unit=unit) if float(amount) > 0 else None


def parse_duration(phrase):
    values = set(_values(_text(phrase), DURATIONS))
    if len(values) != 1:
        return None
    n, unit = next(iter(values))
    return Duration(value=int(n), unit=unit) if n.isdigit() and int(n) > 0 else None


def _grid(text):
    slots = {slot: '1' if any(re.search(r'(?<!\w)' + re.escape(w) + r'(?!\w)', text) for w in words) else '0'
             for slot, words in SLOTS.items()}
    return Grid(**slots) if '1' in slots.values() else None


def parse_timing(phrase):
    text = _text(phrase)
    if not text:
        return None
    steps = re.split(r'\bthen\b|फिर', text)
    if len(steps) > 1:
        parsed = []
        for step in steps:
            dose, duration = parse_dose(step), parse_duration(step)
            if not dose or not duration:
                return None
            parsed.append(TaperStep(dose=dose, duration=duration, when=_grid(step)))
        return Taper(steps=parsed)
    if any(w in text for w in ('as needed', 'when needed', 'ज़रूरत', 'जरूरत', 'sos', 'prn')):
        ns = re.findall(r'\d+', text)
        maximum = int(ns[0]) if len(ns) == 1 and any(w in text for w in ('max', 'at most', 'no more', 'not more', 'ज़्यादा नहीं', 'ज्यादा नहीं')) else None
        return AsNeeded(max_per_day=maximum)
    if re.fullmatch(r'\s*[01](?:[\s-]+[01]){2,3}\s*', text):
        values = re.findall(r'\d', text)
        if len(values) == 3:
            values.insert(2, '0')
        return Grid(**dict(zip('maen', values)))
    grid = _grid(text)
    if grid:
        return grid
    known = {'once daily': 1, 'once a day': 1, 'od': 1, 'daily': 1, 'twice daily': 2, 'twice a day': 2, 'bd': 2,
             'tds': 3, 'three times daily': 3}
    if text.strip() in known:
        return Frequency(times=known[text.strip()], period='day')
    if any(w in text for w in ('दिन में', 'రోజుకి', 'times a day', 'times daily')):
        ns = re.findall(r'\d+', text)
        if len(ns) == 1 and int(ns[0]) > 0:
            return Frequency(times=int(ns[0]), period='day')
    return None


def parse_meal(phrase):
    """(food rule, slots) for a phrase that ties the medicine to meals, or None. Meals with a missing
    relation, or with different relations ("before breakfast and after dinner"), give None."""
    text = _text(phrase)
    pairs = set()
    for slot, words in MEALS.items():
        for word in words:
            for match in re.finditer(re.escape(word), text):
                before = RELATION_BEFORE.search(text[max(0, match.start() - 12):match.start()])
                after = RELATION_AFTER.match(text[match.end():match.end() + 12])
                relation = (before or after)
                if relation is None:
                    return None
                pairs.add((RELATIONS[relation[1]], slot))
    foods = {food for food, _ in pairs}
    return (foods.pop(), {slot for _, slot in pairs}) if len(foods) == 1 else None


def parse_food(phrase):
    text = _text(phrase)
    found = {key for key, terms in FOODS.items() if any(w in text for w in terms)}
    meal = parse_meal(phrase)
    if meal:
        found.add(meal[0])
    return found.pop() if len(found) == 1 else None


def parse_start(phrase, visit_date: date):
    if not phrase:
        return Start()
    text = _text(phrase)
    if 'tomorrow' in text or 'कल से' in text:
        return Start(condition='tomorrow', date=visit_date + timedelta(days=1))
    if 'today' in text or 'आज' in text:
        return Start(condition='today', date=visit_date)
    try:
        value = date.fromisoformat(text.strip())
        return Start(condition='date', date=value)
    except ValueError:
        return None
