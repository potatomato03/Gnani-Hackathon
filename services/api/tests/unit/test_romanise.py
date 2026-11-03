from voicerx.pipeline.romanise import english_loanwords, romanise


def test_english_words_written_in_devanagari_come_back_as_english():
    # Prisma wrote the English of a Hinglish dictation in Devanagari (runbook C-72).
    assert english_loanwords('वन कैप्सूल') == 'one capsule'
    assert english_loanwords('ब्रेकफास्ट के पहले') == 'breakfast के पहले'
    assert english_loanwords('ओरली') == 'orally'
    assert english_loanwords('पाँच दिन') == 'पाँच दिन'


def test_a_devanagari_name_is_spelt_out_in_latin_letters():
    assert romanise('डोलो कैप्सूल') == 'dolo capsule'
    assert romanise('पैरासिटामोल') == 'parasitamol'
    assert romanise('Dolo six fifty') == 'Dolo six fifty'


def test_a_romanised_generic_finds_its_ingredient_by_sound():
    from conftest import REPO_ROOT
    from voicerx.pipeline.complete import generic_product, load_generics
    product = generic_product(romanise('पैरासिटामोल 650'), load_generics(REPO_ROOT))
    assert product.components[0].ingredient == 'Paracetamol' and product.components[0].strength == '650'


def test_english_written_in_gujarati_script_is_read_too():
    assert english_loanwords('એક કેપ્સ્યુલ') == 'એક capsule'
    assert romanise('ડોલો કેપ્સ્યુલ') == 'dolo capsule'
