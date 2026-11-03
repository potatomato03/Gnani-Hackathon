"""Fill in what the doctor left unsaid, after the checks (runbook D-118).

Doctors name a generic, mispronounce a brand they prescribe daily, and rarely say "one tablet". Asking them to
fix each by hand made nine in ten medicines need a click. This step names the product when the evidence is
clear and fills standard values, marking every filled field in `filled` so the review screen shows it; the
doctor's approval of the whole draft is the check. Sound-alike siblings, a strength the product lacks, an
unknown name and allergy conflicts still block.
"""
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
import re

from ..contracts.medication import Dose, Grid, Taper
from ..reference import Component, Product
from ..standard import DOSE_FORMS, proposals
from .check_extraction import MEDICINE_CODES, issue, medicine_issues
from .match_medicine import name_tokens
from .numbers import words_to_digits

FORM_WORDS = {'tablet': 'tablet', 'tab': 'tablet', 'capsule': 'capsule', 'cap': 'capsule', 'syrup': 'syrup',
              'suspension': 'suspension', 'injection': 'injection', 'drops': 'drops', 'gel': 'gel', 'cream': 'cream',
              'inhaler': 'inhaler', 'sachet': 'sachet'}
PRESCRIBED = ('start', 'change', 'continue')


@lru_cache(maxsize=None)
def load_generics(repo_root):
    path = Path(repo_root) / 'data/formulary/generic_names.txt'
    return frozenset(line.strip() for line in path.read_text(encoding='utf-8').splitlines()
                     if line.strip() and not line.startswith('#'))


def generic_product(spoken, generics):
    """A generic named by its ingredient ("Paracetamol 650", "domperidone"), at the strength said, or None."""
    words = [w for w in re.split(r'[\s\-]+', words_to_digits(spoken.lower())) if w]
    for size in (3, 2, 1):
        name = ' '.join(words[:size])
        if len(words) >= size and name in generics:
            rest = words[size:]
            break
    else:
        return None
    numbers = [w for w in rest if re.fullmatch(r'\d+(?:\.\d+)?', w)]
    strength = format(Decimal(numbers[0]).normalize(), 'f') if numbers else ''
    unit = ('mcg' if 'mcg' in rest else 'ml' if 'ml' in rest else 'mg') if strength else ''
    form = next((FORM_WORDS[w] for w in rest if w in FORM_WORDS), 'tablet')
    title = name.title()
    slug = re.sub(r'[^a-z0-9]+', '-', name) + (f'-{strength}' if strength else '')
    return Product(id=f'g-{slug}', brand=f'{title} {strength}'.strip(), manufacturer='generic', form=form,
                   release_type='not_stated', components=[Component(ingredient=title, strength=strength, unit=unit)],
                   aliases=[])


def _said_strengths(text):
    return set(re.findall(r'\d+(?:\.\d+)?', words_to_digits(text.lower())))


def _strength_fits(rx, product):
    said = _said_strengths(rx.spoken_name)
    have = {format(Decimal(c.strength).normalize(), 'f') for c in product.components if c.strength}
    return not said or said <= have


def _choose(rx, products, generics, finder):
    """(product, how) for a medicine the matcher couldn't name exactly, or None to leave it for the doctor."""
    found = finder(rx) if finder else None
    if found and found[1] == 'learned':
        return found
    for name in dict.fromkeys([rx.spoken_name, rx.quotes.get('name_quote', '')]):
        product = generic_product(name, generics) if name else None
        if product and rx.match == 'unmatched':
            return product, 'generic'
    if rx.match == 'ambiguous' and rx.fuzzy and len(rx.candidate_ids) == 1:
        product = products.get(rx.candidate_ids[0])
        if product and _strength_fits(rx, product):
            return product, 'auto'
    # A bare name with formulary siblings ("Pan": Pan 40 or Pan-D) waits for the doctor (D-92).
    return found if rx.match == 'unmatched' else None


def _bare_number(phrase):
    text = words_to_digits((phrase or '').lower()).strip(' .,')
    return text if re.fullmatch(r'\d+(?:\.\d+)?', text) else None


def complete(checked, reference, rules, allergies, finder=None, generics=frozenset()):
    """The checked extraction with clear products named and unsaid values filled, and the reference extended
    by any product it now uses. Medicine flags are recomputed; other flags stay as they were."""
    checked = checked.model_copy(deep=True)
    products = dict(reference.products)
    for rx in checked.medications:
        if rx.match != 'exact':
            choice = _choose(rx, products, generics, finder)
            if choice:
                product, how = choice
                products[product.id] = product
                rx.match, rx.product_id, rx.candidate_ids, rx.fuzzy = 'exact', product.id, [product.id], False
                rx.filled['product'] = how
        product = products.get(rx.product_id) if rx.match == 'exact' else None
        if not product or rx.action not in PRESCRIBED:
            continue
        number = _bare_number(rx.quotes.get('dose_phrase'))
        if rx.dose is None and number and not isinstance(rx.schedule, Taper) and product.form in DOSE_FORMS:
            # "one Pan D": the number was said, the unit is the product's form.
            rx.dose = Dose(amount=number, unit=product.form)
            rx.filled['dose'] = 'unit'
            rx.unresolved = [x for x in rx.unresolved if x != 'dose_phrase']
        for item in proposals(rx, [c.ingredient for c in product.components], product.form, rules):
            if item['action'] == 'set_dose':
                rx.dose, rx.filled['dose'] = Dose(**item['value']), 'standard'
            elif item['action'] == 'set_food':
                rx.food, rx.filled['food'] = item['value']['food'], 'standard'
            elif item['action'] == 'set_timing':
                rx.schedule, rx.filled['schedule'] = Grid(**item['value']['schedule']), 'standard'
    reference = reference.model_copy(update={'products': products})
    ids = {rx.id for rx in checked.medications}
    kept = [i for i in checked.issues if not (i.code in MEDICINE_CODES and i.target in ids)]
    fresh = medicine_issues(checked.medications, reference, allergies)
    fresh += [issue('strength_not_stated', rx.id, 'warn') for rx in checked.medications
              if rx.filled.get('product') == 'generic' and not any(c.strength for c in products[rx.product_id].components)]
    checked.issues = kept + fresh
    return checked, reference
