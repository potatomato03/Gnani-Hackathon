"""Standard instructions for common medicines, proposed where the doctor left a detail unsaid (runbook D-115).

Rules are by ingredient, so one covers every brand: pantoprazole covers Pan 40, Pantop and Pantocid. A
proposal is a correction the doctor accepts with one click, never a change made on its own; what was said
always wins, and duration is never proposed.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

import yaml

from .contracts.medication import Frequency, Taper

SLOTS = {'morning': 'm', 'afternoon': 'a', 'evening': 'e', 'night': 'n'}
# Twice a day is morning and night, three times adds the afternoon, four times is every slot.
DAILY_SLOTS = {2: 'mn', 3: 'man', 4: 'maen'}
FOOD_TEXT = {'after_food': 'after food', 'before_food': 'before food', 'with_food': 'with food',
             'empty_stomach': 'empty stomach'}
DOSE_FORMS = ('tablet', 'capsule')


@dataclass(frozen=True)
class Rules:
    rules: tuple
    reviewed: bool


@lru_cache(maxsize=None)
def load_rules(repo_root):
    data = yaml.safe_load((Path(repo_root) / 'data/rules/standard_instructions.yaml').read_text(encoding='utf-8'))
    return Rules(rules=tuple(data['rules']), reviewed=bool(data['reviewed']))


def _words(text):
    return re.sub(r'[^a-z ]+', ' ', text.lower()).split()


def _rule_for(ingredient, rules):
    """The rule whose ingredient name opens this ingredient's name: 'Pantoprazole Sodium' -> pantoprazole."""
    words = _words(ingredient)
    for rule in rules.rules:
        if any(words[:len(_words(name))] == _words(name) for name in rule['ingredients']):
            return rule
    return None


def standard_for(ingredients, rules):
    """(food, once-daily time, ingredients the rules came from). A field the ingredients disagree on is None;
    an ingredient without a value for a field doesn't count against the others."""
    found = [(name, _rule_for(name, rules)) for name in ingredients]
    found = [(name, rule) for name, rule in found if rule]
    values = []
    for field in ('food', 'once_daily'):
        seen = {rule[field] for _, rule in found if rule.get(field)}
        values.append(seen.pop() if len(seen) == 1 else None)
    return values[0], values[1], [name.lower() for name, _ in found]


def _grid(slots):
    return {'type': 'grid', **{k: '1' if k in slots else '0' for k in 'maen'}}


def proposals(rx, ingredients, form, rules):
    """Corrections for the details rx leaves unsaid, each with display text and an audit reason."""
    food, once_daily, basis = standard_for(ingredients, rules)
    reviewed = '' if rules.reviewed else ', not yet reviewed by a clinician'
    usual = f"Standard instruction for {' + '.join(basis)}{reviewed}; accepted by the doctor." if basis else (
        f'Usual times for this frequency{reviewed}; accepted by the doctor.')
    items = []
    # A taper carries its doses in its steps.
    if rx.dose is None and not isinstance(rx.schedule, Taper) and form in DOSE_FORMS:
        items.append({'action': 'set_dose', 'value': {'amount': '1', 'unit': form}, 'text': f'1 {form}',
                      'reason': f'Standard: one {form} a time{reviewed}; accepted by the doctor.'})
    if rx.food is None and food:
        items.append({'action': 'set_food', 'value': {'food': food}, 'text': FOOD_TEXT[food], 'reason': usual})
    if isinstance(rx.schedule, Frequency) and rx.schedule.period == 'day':
        slots = SLOTS[once_daily] if rx.schedule.times == 1 and once_daily else DAILY_SLOTS.get(rx.schedule.times)
        if slots:
            text = ' and '.join(name for name, key in SLOTS.items() if key in slots)
            items.append({'action': 'set_timing', 'value': {'schedule': _grid(slots)}, 'text': text,
                          'reason': usual if rx.schedule.times == 1 else
                          f'Usual times for {rx.schedule.times} times a day{reviewed}; accepted by the doctor.'})
    return items
