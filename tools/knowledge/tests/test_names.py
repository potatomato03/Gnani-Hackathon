from names import ingredient_key, ingredients_of


def test_indian_and_british_names_map_to_us_label_names():
    assert ingredient_key('Paracetamol') == 'acetaminophen'
    assert ingredient_key('Amoxycillin') == 'amoxicillin'
    assert ingredient_key('Salbutamol') == 'albuterol'
    assert ingredient_key('Levosalbutamol') == 'levalbuterol'
    assert ingredient_key('Glibenclamide') == 'glyburide'
    assert ingredient_key('Tazobactum') == 'tazobactam'
    assert ingredient_key('Sulphamethoxazole') == 'sulfamethoxazole'
    assert ingredient_key('Aluminium Hydroxide') == 'aluminum hydroxide'
    assert ingredient_key('Acetylsalicylic acid') == ingredient_key('ASPIRIN') == 'aspirin'
    assert ingredient_key('Vitamin D3') == ingredient_key('CHOLECALCIFEROL') == 'cholecalciferol'
    assert ingredient_key('Ursodeoxycholic Acid') == 'ursodiol'


def test_salt_words_are_dropped_on_both_sides():
    assert ingredient_key('Metoprolol Succinate') == ingredient_key('METOPROLOL SUCCINATE') == 'metoprolol'
    assert ingredient_key('AMLODIPINE BESYLATE') == ingredient_key('Amlodipine') == 'amlodipine'
    assert ingredient_key('Escitalopram Oxalate') == 'escitalopram'
    assert ingredient_key('Chlorpheniramine Maleate') == 'chlorpheniramine'


def test_salt_words_that_are_the_whole_name_are_kept():
    # "Sodium chloride" must not shrink to "chloride", nor "Potassium" to nothing.
    assert ingredient_key('Sodium Chloride') == 'sodium chloride'
    assert ingredient_key('Potassium Chloride') == 'potassium chloride'
    assert ingredient_key('Calcium Carbonate') == 'calcium carbonate'


def test_compositions_split_into_ingredients_without_strengths():
    assert ingredients_of('Amoxycillin  (500mg) +  Clavulanic Acid (125mg)') == {'amoxicillin', 'clavulanic acid'}
    assert ingredients_of('Paracetamol (650mg)') == {'acetaminophen'}
    assert ingredients_of('') == set()
