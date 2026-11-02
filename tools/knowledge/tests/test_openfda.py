from openfda import label_chunks, select_labels


def label(substances, kind='HUMAN PRESCRIPTION DRUG', date='20240101', set_id='s1', route='ORAL', **sections):
    return {'set_id': set_id, 'effective_time': date,
            'openfda': {'substance_name': substances, 'generic_name': [' AND '.join(substances)],
                        'product_type': [kind], 'route': [route], 'pharm_class_epc': ['Angiotensin 2 Receptor Blocker [EPC]']},
            **{k: [v] for k, v in sections.items()}}


def test_only_labels_whose_every_ingredient_is_sold_in_india_are_kept():
    india = {'telmisartan', 'acetaminophen'}
    kept = select_labels([label(['TELMISARTAN']), label(['TELMISARTAN', 'AMLODIPINE BESYLATE'], set_id='s2'),
                          label(['ACETAMINOPHEN'], set_id='s3')], india)
    assert {r['set_id'] for r in kept.values()} == {'s1', 's3'}


def test_labels_without_a_known_substance_are_skipped():
    record = label(['TELMISARTAN'])
    record['openfda'] = {}
    assert select_labels([record], {'telmisartan'}) == {}


def test_prescription_label_beats_otc_then_fuller_then_newer():
    india = {'acetaminophen'}
    otc = label(['ACETAMINOPHEN'], kind='HUMAN OTC DRUG', date='20260101', set_id='otc', indications_and_usage='x')
    thin = label(['ACETAMINOPHEN'], date='20250101', set_id='thin', indications_and_usage='x')
    full = label(['ACETAMINOPHEN'], date='20200101', set_id='full', indications_and_usage='x', warnings='y')
    newer_full = label(['ACETAMINOPHEN'], date='20230101', set_id='newer', indications_and_usage='x', warnings='y')
    kept = select_labels([otc, thin, full, newer_full], india)
    assert [r['set_id'] for r in kept.values()] == ['newer']


def test_routes_are_kept_apart():
    india = {'clobetasol'}
    kept = select_labels([label(['CLOBETASOL PROPIONATE'], route='TOPICAL'), label(['CLOBETASOL PROPIONATE'], route='ORAL', set_id='s2')], india)
    assert len(kept) == 2


def test_title_comes_from_substances_not_the_labels_own_generic_name():
    record = label(['ACETAMINOPHEN'], indications_and_usage='Uses: pain.')
    record['openfda']['generic_name'] = ['Redicare non-aspirin, acetaminophen 500mg']
    assert label_chunks(record)[0]['title'] == 'Acetaminophen'


def test_chunks_carry_heading_section_and_citation():
    record = label(['TELMISARTAN'], indications_and_usage='1 INDICATIONS AND USAGE Telmisartan tablets are indicated for the treatment of hypertension.',
                   clinical_studies='Not chunked.')
    chunks = label_chunks(record)
    assert [c['section'] for c in chunks] == ['Uses']
    chunk = chunks[0]
    assert chunk['text'] == 'Telmisartan (oral; Angiotensin 2 Receptor Blocker). Uses: Telmisartan tablets are indicated for the treatment of hypertension.'
    assert chunk['ingredients'] == ['telmisartan'] and chunk['source'] == 'openfda_label'
    assert chunk['url'] == 'https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=s1'
    assert chunk['id'] == 's1:indications_and_usage:1'
