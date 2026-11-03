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
