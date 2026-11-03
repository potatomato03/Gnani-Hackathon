from conftest import REPO_ROOT, make_draft, resolved_medicine
from voicerx.app.catalog import CatalogEntry, NameIndex, product_from_row
from voicerx.app.shortlist import Choice, Shortlist, build_items, conditions_of, make_shortlist
from voicerx.pipeline.complete import load_generics
from voicerx.standard import load_rules

INDEX = NameIndex([
    CatalogEntry('in-1', 'Zerodol-P Tablet', 'Aceclofenac (100mg) + Paracetamol (325mg)', 'indian', popularity=0.9),
    CatalogEntry('in-2', 'Combiflam Tablet', 'Ibuprofen (400mg) + Paracetamol (325mg)', 'indian', popularity=0.9),
    CatalogEntry('in-3', 'Combiflam Suspension', 'Ibuprofen (100mg) + Paracetamol (162.5mg)', 'indian', popularity=0.8),
])
ROWS = {e.id: e for e in INDEX.entries}
lookup = lambda pid: product_from_row(pid, ROWS[pid].name, '', ROWS[pid].composition) if pid in ROWS else None
GENERICS, RULES = load_generics(REPO_ROOT), load_rules(REPO_ROOT)


def choices(*items):
    return Shortlist(items=[Choice(generic=g, strength=s, brand=b, why='pain', group='Pain') for g, s, b in items])


def test_named_choices_become_real_products_in_the_models_order():
    ranking = choices(('Ibuprofen + Paracetamol', '400 mg + 325 mg', 'Combiflam'),
                      ('Aceclofenac + Paracetamol', '100 mg + 325 mg', 'Zerodol-P'),
                      ('Pantoprazole', '40 mg', 'Nobrandatall'))
    items = build_items(ranking, [INDEX], GENERICS, RULES, lookup)
    assert [i['product_id'] for i in items] == ['in-2', 'in-1', 'g-pantoprazole-40']
    # An adult gets the tablet, not the syrup of the same brand; the standard food rule comes along.
    assert items[0]['form'] == 'tablet' and items[0]['food'] == 'after_food'
    assert items[2]['food'] == 'before_food' and items[2]['once_daily'] == 'morning'


def test_a_choice_that_is_neither_a_known_brand_nor_a_single_generic_is_dropped():
    ranking = choices(('Herbal mix + Something', '1 g', 'Nonesuch'))
    assert build_items(ranking, [INDEX], GENERICS, RULES, lookup) == []


def test_conditions_are_the_present_findings_about_the_patient():
    from voicerx.contracts.extraction import ExtractedItem
    draft = make_draft([resolved_medicine()])
    base = dict(certainty='stated', temporality='current', laterality=None, subject='patient', said_by='doctor')
    kept = [ExtractedItem(**base, id='x1', kind='symptom', term='knee pain', quote='q', assertion='present'),
            ExtractedItem(**base, id='x2', kind='diagnosis', term='ACL tear', quote='q', assertion='present'),
            ExtractedItem(**base, id='x3', kind='symptom', term='fever', quote='q', assertion='absent')]
    draft = draft.model_copy(update={'checked': draft.checked.model_copy(update={'kept': kept})})
    assert conditions_of(draft) == ['ACL tear', 'knee pain']


def test_no_conditions_or_a_failed_model_gives_an_empty_list():
    class Broken:
        def generate(self, *args):
            raise RuntimeError('quota')
    assert make_shortlist(Broken(), [], [INDEX], GENERICS, RULES, lookup)[0] == []
    assert make_shortlist(Broken(), ['knee pain'], [INDEX], GENERICS, RULES, lookup)[0] == []


def test_a_brand_whose_ingredients_differ_from_the_named_generic_is_never_used():
    # "Crocin 500" (paracetamol) sounded like "Rocin 500" (azithromycin); the generic is used instead.
    index = NameIndex([CatalogEntry('in-9', 'Rocin 500mg Tablet', 'Azithromycin (500mg)', 'indian', popularity=0.6)])
    rows = {e.id: e for e in index.entries}
    find = lambda pid: product_from_row(pid, rows[pid].name, '', rows[pid].composition) if pid in rows else None
    items = build_items(choices(('Paracetamol', '500 mg', 'Crocin')), [index], GENERICS, RULES, find)
    assert [i['product_id'] for i in items] == ['g-paracetamol-500']


def test_each_choice_keeps_its_purpose_and_the_prompt_asks_for_companions():
    from voicerx.app.shortlist import MAX_ITEMS, PROMPT_VERSION, SYSTEM
    items = build_items(choices(('Ibuprofen + Paracetamol', '400 mg + 325 mg', 'Combiflam')), [INDEX], GENERICS, RULES, lookup)
    assert items[0]['group'] == 'Pain'
    assert PROMPT_VERSION == 'shortlist-v2' and MAX_ITEMS == 8 and 'stomach' in SYSTEM
