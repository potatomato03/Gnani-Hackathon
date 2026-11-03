from conftest import REPO_ROOT, resolved_medicine
from voicerx.contracts.medication import AsNeeded, Dose, Frequency, Grid
from voicerx.standard import load_rules, proposals, standard_for

RULES = load_rules(REPO_ROOT)


def by_action(items):
    return {p['action']: p['value'] for p in items}


def test_a_combination_takes_what_its_ingredients_agree_on():
    assert standard_for(['Domperidone', 'Pantoprazole'], RULES)[:2] == ('before_food', 'morning')
    assert standard_for(['Ibuprofen', 'Paracetamol'], RULES)[:2] == ('after_food', None)
    # An ingredient with no food rule (amoxycillin) doesn't block the one that has one.
    assert standard_for(['Amoxycillin', 'Clavulanic Acid'], RULES)[:2] == ('with_food', None)
    assert standard_for(['Levocetirizine', 'Montelukast'], RULES)[:2] == (None, 'night')


def test_ingredients_that_disagree_give_no_standard():
    assert standard_for(['Domperidone', 'Paracetamol'], RULES)[:2] == (None, None)
    assert standard_for(['Collagen Peptide'], RULES)[:2] == (None, None)


def test_salt_names_find_their_ingredient():
    assert standard_for(['Pantoprazole Sodium'], RULES)[:2] == ('before_food', 'morning')


def test_unsaid_dose_food_and_once_daily_time_are_proposed():
    rx = resolved_medicine(product_id='p-pan-40', dose=None, food=None, schedule=Frequency(times=1, period='day'))
    found = by_action(proposals(rx, ['Pantoprazole'], 'tablet', RULES))
    assert found == {'set_dose': {'amount': '1', 'unit': 'tablet'}, 'set_food': {'food': 'before_food'},
                     'set_timing': {'schedule': {'type': 'grid', 'm': '1', 'a': '0', 'e': '0', 'n': '0'}}}


def test_what_the_doctor_said_is_never_replaced():
    rx = resolved_medicine(dose=Dose(amount='2', unit='tablet'), food='before_food',
                           schedule=Grid(m='0', a='0', e='0', n='1'))
    assert proposals(rx, ['Paracetamol'], 'tablet', RULES) == []


def test_twice_and_three_times_daily_take_the_usual_slots_for_any_medicine():
    for times, slots in ((2, ('1', '0', '0', '1')), (3, ('1', '1', '0', '1')), (4, ('1', '1', '1', '1'))):
        rx = resolved_medicine(schedule=Frequency(times=times, period='day'))
        timing = by_action(proposals(rx, ['Collagen Peptide'], 'sachet', RULES))['set_timing']['schedule']
        assert (timing['m'], timing['a'], timing['e'], timing['n']) == slots


def test_once_daily_without_a_known_time_and_unsaid_timing_stay_for_the_doctor():
    once = resolved_medicine(schedule=Frequency(times=1, period='day'), food=None)
    assert 'set_timing' not in by_action(proposals(once, ['Collagen Peptide'], 'sachet', RULES))
    unsaid = resolved_medicine(product_id='p-pan-40', schedule=None)
    assert 'set_timing' not in by_action(proposals(unsaid, ['Pantoprazole'], 'tablet', RULES))
    weekly = resolved_medicine(schedule=Frequency(times=1, period='week'))
    assert 'set_timing' not in by_action(proposals(weekly, ['Pantoprazole'], 'tablet', RULES))


def test_a_dose_is_proposed_only_for_tablets_capsules_and_sachets():
    rx = resolved_medicine(dose=None)
    assert by_action(proposals(rx, ['Paracetamol'], 'capsule', RULES))['set_dose'] == {'amount': '1', 'unit': 'capsule'}
    assert by_action(proposals(rx, ['Collagen Peptide'], 'sachet', RULES))['set_dose'] == {'amount': '1', 'unit': 'sachet'}
    assert 'set_dose' not in by_action(proposals(rx, ['Paracetamol'], 'syrup', RULES))


def test_as_needed_is_left_alone_and_every_proposal_says_it_is_unreviewed():
    rx = resolved_medicine(schedule=AsNeeded(), food=None)
    items = proposals(rx, ['Paracetamol'], 'tablet', RULES)
    assert by_action(items) == {'set_food': {'food': 'after_food'}}
    assert 'not yet reviewed' in items[0]['reason'] and items[0]['text'] == 'after food'
    assert RULES.reviewed is False
