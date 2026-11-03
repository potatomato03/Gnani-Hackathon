from conftest import REPO_ROOT, resolved_medicine
from voicerx.contracts.extraction import CheckedExtraction
from voicerx.contracts.medication import Dose, Frequency
from voicerx.pipeline.check_extraction import medicine_issues
from voicerx.pipeline.complete import complete, load_generics
from voicerx.reference import load_reference
from voicerx.standard import load_rules

REF = load_reference(REPO_ROOT)
RULES = load_rules(REPO_ROOT)
GENERICS = load_generics(REPO_ROOT)


def checked(*meds):
    return CheckedExtraction(transcript_sha256='x', kept=[], dropped=[], medications=list(meds), corrections=[],
                             issues=medicine_issues(list(meds), REF, None))


def run(*meds, finder=None):
    done, reference = complete(checked(*meds), REF, RULES, None, finder=finder, generics=GENERICS)
    return done, reference


def unknown(spoken, **changes):
    return resolved_medicine(spoken_name=spoken, match='unmatched', product_id=None, candidate_ids=[], dose=None,
                             food=None, quotes={'name_quote': spoken}, **changes)


def codes(done):
    return {(i.code, i.severity) for i in done.issues}


def test_a_generic_name_becomes_that_ingredient_at_the_said_strength():
    done, reference = run(unknown('Paracetamol 650'))
    rx = done.medications[0]
    product = reference.products[rx.product_id]
    assert (rx.match, product.form, product.components[0].strength) == ('exact', 'tablet', '650')
    assert rx.dose == Dose(amount='1', unit='tablet') and rx.food == 'after_food'
    assert rx.filled == {'product': 'generic', 'dose': 'standard', 'food': 'standard'}
    assert codes(done) == set()


def test_a_generic_without_a_strength_is_kept_and_flagged():
    done, reference = run(unknown('domperidone'))
    assert done.medications[0].match == 'exact'
    assert ('strength_not_stated', 'warn') in codes(done)


def test_a_close_spelling_with_one_candidate_and_the_same_strength_is_taken():
    rx = resolved_medicine(spoken_name='Dollo 650', match='ambiguous', fuzzy=True, product_id=None,
                           candidate_ids=['p-dolo-650'], quotes={'name_quote': 'Dollo 650'})
    rx = run(rx)[0].medications[0]
    assert (rx.match, rx.product_id, rx.filled['product']) == ('exact', 'p-dolo-650', 'auto')


def test_a_strength_the_product_lacks_is_left_for_the_doctor():
    rx = resolved_medicine(spoken_name='Combyflam six fifty', match='ambiguous', fuzzy=True, product_id=None,
                           candidate_ids=['p-combiflam'], quotes={'name_quote': 'Combyflam'})
    done = run(rx)[0]
    assert done.medications[0].match == 'ambiguous' and ('fuzzy_product_match', 'block') in codes(done)


def test_sound_alike_siblings_are_never_chosen_unless_the_doctor_chose_before():
    bare = resolved_medicine(spoken_name='Pan', match='ambiguous', product_id=None,
                             candidate_ids=['p-pan-40', 'p-pan-d'], quotes={'name_quote': 'Pan'})
    assert run(bare)[0].medications[0].match == 'ambiguous'
    learned = run(bare, finder=lambda rx: (REF.products['p-pan-40'], 'learned'))[0].medications[0]
    assert (learned.product_id, learned.filled['product']) == ('p-pan-40', 'learned')


def test_a_bare_number_said_as_the_dose_takes_the_products_unit():
    rx = resolved_medicine(spoken_name='Pan D', product_id='p-pan-d', candidate_ids=['p-pan-d'], dose=None,
                           unresolved=['dose_phrase'], quotes={'name_quote': 'Pan D', 'dose_phrase': 'one'})
    rx = run(rx)[0].medications[0]
    assert rx.dose == Dose(amount='1', unit='capsule') and rx.filled['dose'] == 'unit'
    assert 'dose_phrase' not in rx.unresolved


def test_what_was_said_stays_and_nothing_is_marked():
    rx = resolved_medicine(schedule=Frequency(times=2, period='day'), food='before_food')
    rx = run(rx)[0].medications[0]
    assert rx.food == 'before_food' and rx.dose == Dose(amount='1', unit='tablet')
    assert rx.filled == {'schedule': 'standard'}


def test_a_generic_written_in_devanagari_is_recognised_with_its_said_dose():
    rx = unknown('पैरासिटामोल').model_copy(update={'quotes': {'name_quote': 'पैरासिटामोल', 'dose_phrase': 'एक'}})
    done, reference = run(rx)
    rx = done.medications[0]
    assert reference.products[rx.product_id].components[0].ingredient == 'Paracetamol'
    assert rx.dose == Dose(amount='1', unit='tablet') and rx.filled['dose'] == 'unit'
