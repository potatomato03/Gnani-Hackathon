from voicerx.app.catalog import (CatalogEntry, NameIndex, brand_stem, parse_composition, product_from_row,
                                 sound_key, strengths)


def test_compositions_become_components_with_strengths():
    parts = parse_composition('Amoxycillin  (500mg) + Clavulanic Acid (125mg)')
    assert [(c.ingredient, c.strength, c.unit) for c in parts] == [('Amoxycillin', '500', 'mg'), ('Clavulanic Acid', '125', 'mg')]
    assert [(c.ingredient, c.strength, c.unit) for c in parse_composition('Collagen Peptide')] == [('Collagen Peptide', '', '')]


def test_an_indian_product_row_becomes_a_product_with_its_tier_in_the_id():
    product = product_from_row('in-42', 'PAN 40 Tablet', 'Alkem Laboratories Ltd', 'Pantoprazole (40mg)')
    assert product.id == 'in-42' and product.brand == 'PAN 40' and product.form == 'tablet'
    assert product.components[0].ingredient == 'Pantoprazole' and product.components[0].strength == '40'


def test_stems_drop_forms_but_keep_what_tells_products_apart():
    assert brand_stem('Pan-D Capsule PR') == 'pan d'
    assert brand_stem('PAN 40 Tablet') == 'pan'
    assert brand_stem('Combiflam Tablet') == 'combiflam'


def test_sound_keys_fold_the_letters_speech_recognition_confuses():
    assert sound_key('man') == sound_key('pan') == sound_key('ban')
    assert sound_key('kombyflam') == sound_key('combiflam')
    assert sound_key('vysolon') == sound_key('wysolone')
    assert sound_key('montier lc') == sound_key('montair lc')
    assert sound_key('pan') != sound_key('pan d')
    # Vowel positions stay, so unrelated names no longer collapse to one key (first measurement, 3 Nov).
    assert sound_key('kolapik') != sound_key('cyclomic')
    assert sound_key('band') != sound_key('bipant')


def test_strengths_come_from_names_and_compositions():
    assert strengths('Mann 40') == {'40'}
    assert strengths('Combyflam 650') == {'650'}
    assert strengths('PAN 40 Tablet', 'Pantoprazole (40mg)') == {'40'}


INDEX = NameIndex([
    CatalogEntry('in-1', 'PAN 40 Tablet', 'Pantoprazole (40mg)', 'indian'),
    CatalogEntry('in-2', 'Pan-D Capsule PR', 'Domperidone (30mg) + Pantoprazole (40mg)', 'indian'),
    CatalogEntry('in-3', 'Pantop 40 Tablet', 'Pantoprazole (40mg)', 'indian'),
    CatalogEntry('in-4', 'Combiflam Tablet', 'Ibuprofen (400mg) + Paracetamol (325mg)', 'indian'),
    CatalogEntry('in-5', 'Mankind 40 Tablet', 'Telmisartan (40mg)', 'indian'),
    CatalogEntry('in-6', 'Wysolone 10 Tablet', 'Prednisolone (10mg)', 'indian'),
    CatalogEntry('in-7', 'Band Aid Strip', 'Adhesive', 'indian'),
])


def test_misheard_names_find_their_sound_alikes_with_matching_strength():
    found = [c.entry.id for c in INDEX.candidates('Mann 40')]
    assert found[0] == 'in-1' and 'in-7' not in found
    assert 'in-1' in [c.entry.id for c in INDEX.candidates('Bann 40')]
    assert 'in-6' in [c.entry.id for c in INDEX.candidates('Vysolon ten')]


def test_a_stated_strength_that_no_candidate_has_leaves_strength_unconfirmed_not_dropped():
    # "Combyflam 650": no Combiflam 650 in the list; the 400/325 product is still offered, marked as a mismatch.
    found = {c.entry.id: c for c in INDEX.candidates('Combyflam 650')}
    assert 'in-4' in found and found['in-4'].strength_match is False


def test_the_sibling_product_is_offered_beside_the_bare_name():
    found = [c.entry.id for c in INDEX.candidates('Pan')]
    assert {'in-1', 'in-2'} <= set(found)


def test_brands_ending_in_letters_also_match_the_letters_spoken():
    from voicerx.app.catalog import spoken_forms
    assert spoken_forms('pan d') == ['pan di', 'pandi']
    assert spoken_forms('montair lc') == ['montair elsi', 'montairelsi']
    assert spoken_forms('taxim o') == ['taxim o', 'taximo']
    # Only a short consonant word after the brand is read as letters; whole words and Hindi stay as they are.
    assert spoken_forms('combiflam') == spoken_forms('dolo') == spoken_forms('pan') == []
    assert spoken_forms('telma plus') == []


def test_a_spoken_letter_written_as_one_word_finds_its_brand():
    from voicerx.app.catalog import similarity
    pan_d = CatalogEntry('in-2', 'Pan-D Capsule PR', 'Domperidone (30mg) + Pantoprazole (40mg)', 'indian')
    lookalike = CatalogEntry('in-8', 'Panday 40mg Tablet', 'Pantoprazole (40mg)', 'indian')
    assert similarity('Pandie', pan_d) >= similarity('Pandie', lookalike)
    assert similarity('Pandee', pan_d) >= 0.95 and similarity('Pan Dee', pan_d) >= 0.95
    # A different ending is not the letter: "Panto" still sounds more like Pantop than Pan-D.
    pantop = CatalogEntry('in-3', 'Pantop 40 Tablet', 'Pantoprazole (40mg)', 'indian')
    assert similarity('Panto', pantop) > similarity('Panto', pan_d)


def test_a_widely_sold_brand_leads_an_obscure_one_that_sounds_as_close():
    index = NameIndex([
        CatalogEntry('in-2', 'Pan-D Capsule PR', 'Domperidone (30mg) + Pantoprazole (40mg)', 'indian', popularity=0.88),
        CatalogEntry('in-8', 'Panday 40mg Tablet', 'Pantoprazole (40mg)', 'indian', popularity=0.2),
        CatalogEntry('in-9', 'Pandu 40mg Tablet', 'Pantoprazole (40mg)', 'indian', popularity=0.11),
    ])
    assert [c.entry.id for c in index.candidates('Pandie')][0] == 'in-2'


def test_popularity_counts_less_than_a_clinic_listing():
    from voicerx.app.catalog import LISTED_BONUS, standing
    assert standing(CatalogEntry('p-1', 'Pan 40 tablet', 'Pantoprazole (40mg)', 'formulary')) == LISTED_BONUS
    assert 0 < standing(CatalogEntry('in-1', 'PAN 40 Tablet', 'Pantoprazole (40mg)', 'indian', popularity=1.0)) <= LISTED_BONUS
    assert standing(CatalogEntry('in-5', 'Rare Tablet', 'X (1mg)', 'indian')) == 0
