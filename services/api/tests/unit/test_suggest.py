from voicerx.app.suggest import Ranked, Ranking, heard_key, mark_likely, merge_ranking


def item(sound, **changes):
    return {'sound': sound, 'sound_alike_sibling': False, 'strength_match': True, 'ranked_by_model': True,
            'chosen_before': 0, 'likely': False, **changes}


def test_a_clear_lead_is_likely():
    assert mark_likely([item(0.95), item(0.8)], model_used=True)[0]['likely']


def test_near_ties_siblings_weak_sounds_and_strength_conflicts_stay_possible():
    # Two LC brands that sound equally close.
    assert not mark_likely([item(0.93), item(0.93)], model_used=True)[0]['likely']
    assert not mark_likely([item(0.95, sound_alike_sibling=True)], model_used=True)[0]['likely']
    assert not mark_likely([item(0.78)], model_used=True)[0]['likely']
    assert not mark_likely([item(0.95, strength_match=False)], model_used=True)[0]['likely']
    assert not mark_likely([item(0.95, ranked_by_model=False)], model_used=True)[0]['likely']


def test_the_doctors_earlier_choice_counts_when_the_model_did_not_rank_it():
    assert mark_likely([item(0.9, ranked_by_model=False, chosen_before=2)], model_used=True)[0]['likely']


def test_an_invented_product_never_reaches_the_doctor():
    ranking = Ranking(ranked=[Ranked(id='in-999', reason='made up'), Ranked(id='in-1', reason='antacid before breakfast')])
    order, reasons = merge_ranking(['in-1', 'in-2', 'in-3'], ranking)
    assert order == ['in-1', 'in-2', 'in-3'] and reasons == {'in-1': 'antacid before breakfast'}


def test_without_a_ranking_the_sound_alike_order_stands_with_no_reasons():
    assert merge_ranking(['in-2', 'in-1'], None) == (['in-2', 'in-1'], {})


def test_a_repeated_id_keeps_its_first_place():
    ranking = Ranking(ranked=[Ranked(id='in-2', reason='first'), Ranked(id='in-2', reason='again')])
    assert merge_ranking(['in-1', 'in-2'], ranking) == (['in-2', 'in-1'], {'in-2': 'first'})


def test_heard_words_give_one_key_however_they_are_written():
    assert heard_key('Mann 40') == heard_key('mann forty') == heard_key('MANN 40 tablet') == 'mann 40'


# A clear match is taken without asking (runbook D-118); anything close to a rival is left for the doctor.
def entry(pid, name, composition, tier='indian', popularity=0.0):
    from voicerx.app.catalog import CatalogEntry
    return CatalogEntry(pid, name, composition, tier, popularity=popularity)


def cand(e, score, strength=None):
    from voicerx.app.catalog import Candidate
    return Candidate(e, score, strength)


def test_a_clear_well_known_match_is_taken():
    from voicerx.app.suggest import confident_choice
    wysolone = entry('p-1', 'Wysolone 10 tablet', 'Prednisolone (10mg)', 'formulary')
    obscure = entry('in-2', 'Islon 10mg Tablet', 'Prednisolone (10mg)', popularity=0.05)
    assert confident_choice([cand(wysolone, 0.93, True), cand(obscure, 0.9, True)]).entry.id == 'p-1'


def test_a_close_rival_brand_an_obscure_top_or_a_strength_conflict_leaves_it_to_the_doctor():
    from voicerx.app.suggest import confident_choice
    pan_d = entry('in-1', 'Pan-D Capsule PR', 'Domperidone (30mg) + Pantoprazole (40mg)', popularity=0.88)
    pant_d = entry('in-2', 'Pant D Capsule SR', 'Domperidone (10mg) + Pantoprazole (40mg)', popularity=0.4)
    assert confident_choice([cand(pan_d, 0.95), cand(pant_d, 0.94)]) is None
    assert confident_choice([cand(entry('in-3', 'Panday 40mg Tablet', 'Pantoprazole (40mg)', popularity=0.2), 0.96)]) is None
    assert confident_choice([cand(pan_d, 0.95, False)]) is None
    assert confident_choice([cand(pan_d, 0.8)]) is None


def test_a_stated_strength_only_one_listed_product_shares_allows_a_looser_sound():
    from voicerx.app.suggest import confident_choice
    wysolone_10 = entry('p-1', 'Wysolone 10 tablet', 'Prednisolone (10mg)', 'formulary')
    wysolone_5 = entry('in-2', 'Wysolone 5 Tablet DT', 'Prednisolone (5mg)', popularity=0.8)
    assert confident_choice([cand(wysolone_10, 0.77, True), cand(wysolone_5, 0.77, False)]).entry.id == 'p-1'
    # Two listed products with that strength, sounding alike: Pan 40 or Pan-D for "Mann 40".
    pan_40 = entry('p-2', 'Pan 40 tablet', 'Pantoprazole (40mg)', 'formulary')
    pan_d = entry('p-3', 'Pan capsule', 'Domperidone (30mg) + Pantoprazole (40mg)', 'formulary')
    assert confident_choice([cand(pan_40, 0.83, True), cand(pan_d, 0.83, True)]) is None


def test_one_brand_in_two_strengths_waits_when_no_strength_was_said():
    from voicerx.app.suggest import confident_choice
    telma_40 = entry('in-1', 'Telma 40 Tablet', 'Telmisartan (40mg)', popularity=0.9)
    telma_80 = entry('in-2', 'Telma 80 Tablet', 'Telmisartan (80mg)', popularity=0.8)
    assert confident_choice([cand(telma_40, 0.95), cand(telma_80, 0.95)]) is None
    assert confident_choice([cand(telma_40, 0.95, True), cand(telma_80, 0.95, False)]).entry.id == 'in-1'


def test_a_rival_with_the_same_composition_is_the_same_medicine():
    from voicerx.app.suggest import confident_choice
    montair = entry('p-1', 'Montair-LC tablet', 'Levocetirizine (5mg) + Montelukast (10mg)', 'formulary')
    montor = entry('in-2', 'Montor-LC Tablet', 'Levocetirizine (5mg) + Montelukast (10mg)', popularity=0.4)
    assert confident_choice([cand(montair, 0.9), cand(montor, 0.92)]).entry.id == 'p-1'


def test_a_brand_family_sibling_outside_the_candidates_still_counts():
    from voicerx.app.suggest import confident_choice
    pan_d = entry('p-3', 'Pan-D capsule', 'Domperidone (30mg) + Pantoprazole (40mg)', 'formulary')
    pan_40 = entry('p-2', 'Pan 40 tablet', 'Pantoprazole (40mg)', 'formulary')
    # "Bann 40": Pan-D 0.83, Pan 40 0.71; too close to choose between.
    assert confident_choice([cand(pan_d, 0.83, True)], [pan_d, pan_40], 'Bann 40') is None
    # "Pandee": Pan-D 1.0, Pan 40 well behind.
    assert confident_choice([cand(pan_d, 1.0)], [pan_d, pan_40], 'Pandee').entry.id == 'p-3'


def test_for_an_adult_with_no_form_said_the_tablet_is_taken_over_its_syrup():
    # Runbook D-120: a liquid or injection of the same brand doesn't make an adult's tablet ambiguous.
    from voicerx.app.suggest import confident_choice
    tablet = entry('p-1', 'Combiflam tablet', 'Ibuprofen (400mg) + Paracetamol (325mg)', 'formulary')
    syrup = entry('in-2', 'Combiflam Suspension', 'Ibuprofen (100mg) + Paracetamol (162.5mg)', popularity=0.8)
    found = [cand(tablet, 0.95), cand(syrup, 0.95)]
    assert confident_choice(found, [tablet, syrup], 'Combyflam', adult=True).entry.id == 'p-1'
    assert confident_choice(found, [tablet, syrup], 'Combyflam', adult=False) is None
    # Said as a syrup, the syrup is meant, so the choice stays open.
    assert confident_choice(found, [tablet, syrup], 'Combyflam syrup', adult=True) is None


def test_a_product_on_the_clinics_list_needs_a_little_less_sound():
    from voicerx.app.suggest import confident_choice
    listed = entry('p-1', 'Combiflam tablet', 'Ibuprofen (400mg) + Paracetamol (325mg)', 'formulary')
    obscure = entry('in-2', 'Cypaflam Tablet', 'Ibuprofen (400mg) + Paracetamol (325mg)', popularity=0.05)
    assert confident_choice([cand(listed, 0.86), cand(obscure, 0.82)]).entry.id == 'p-1'
    popular = entry('in-3', 'Combiflam Tablet', 'Ibuprofen (400mg) + Paracetamol (325mg)', popularity=0.9)
    assert confident_choice([cand(popular, 0.86)]) is None


def test_for_an_adult_a_childrens_sachet_of_the_same_drug_yields_to_the_capsule():
    from voicerx.app.suggest import confident_choice
    capsule = entry('in-1', 'Redotil 100mg Capsule', 'Racecadotril (100mg)', popularity=0.76)
    sachet = entry('in-2', 'Redotil Sachet', 'Racecadotril (10mg)', popularity=0.39)
    found = [cand(capsule, 0.93), cand(sachet, 0.93)]
    assert confident_choice(found, [capsule, sachet], 'Redotyl', adult=True).entry.id == 'in-1'
    other = entry('in-3', 'Redomix Sachet', 'Probiotic (1g)', popularity=0.5)
    assert confident_choice([cand(capsule, 0.93), cand(other, 0.92)], [], 'Redotyl', adult=True) is None
