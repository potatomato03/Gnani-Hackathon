from jan_aushadhi import jan_aushadhi_chunks

ROWS = [
    {'Generic Name': 'Telmisartan 40mg Tablets IP', 'Unit Size': "10's", 'Group Name': 'Cardiovascular'},
    {'Generic Name': 'Amlodipine 5mg Tablets', 'Unit Size': "10's", 'Group Name': 'Cardiovascular'},
    {'Generic Name': 'Paracetamol 650mg Tablets', 'Unit Size': "15's", 'Group Name': 'Analgesic/Antipyretic'},
]


def test_one_chunk_per_group_lists_its_generics():
    chunks = jan_aushadhi_chunks(ROWS)
    assert [c['title'] for c in chunks] == ['Analgesic/Antipyretic', 'Cardiovascular']
    cardio = chunks[1]
    assert cardio['text'] == ('Jan Aushadhi (PMBJP) generic medicines in the group "Cardiovascular": '
                              'Amlodipine 5mg Tablets; Telmisartan 40mg Tablets IP.')
    assert cardio['source'] == 'jan_aushadhi' and cardio['ingredients'] == ['amlodipine', 'telmisartan']


def test_ingredients_are_read_from_the_generic_name():
    chunks = jan_aushadhi_chunks([{'Generic Name': 'Aceclofenac 100mg and Paracetamol 325mg Tablets',
                                   'Unit Size': "10's", 'Group Name': 'Analgesic'}])
    assert chunks[0]['ingredients'] == ['aceclofenac', 'acetaminophen']


def test_every_part_of_a_long_group_names_its_group():
    rows = [{'Generic Name': f'Metformin Hydrochloride {n}mg Tablets IP', 'Unit Size': '', 'Group Name': 'Anti-Diabetic'}
            for n in range(100, 400)]
    chunks = jan_aushadhi_chunks(rows)
    assert len(chunks) > 2
    assert all(c['text'].startswith('Jan Aushadhi (PMBJP) generic medicines in the group "Anti-Diabetic"') for c in chunks)
    assert all(len(c['text']) <= 800 for c in chunks)
    assert sum(c['text'].count('Metformin') for c in chunks) == 300


def test_consumables_are_left_out_and_group_spellings_merge():
    rows = [{'Generic Name': 'Ankle Binder Support Large', 'Unit Size': '', 'Group Name': 'Surgical & Medical Consumables'},
            {'Generic Name': 'Aciclovir Tablets IP 400 mg', 'Unit Size': '', 'Group Name': 'Anti-Viral'},
            {'Generic Name': 'Valacyclovir Tablets 500mg', 'Unit Size': '', 'Group Name': 'Anti-viral'}]
    chunks = jan_aushadhi_chunks(rows)
    assert [c['title'] for c in chunks] == ['Anti-Viral'] and 'Valacyclovir' in chunks[0]['text']


def test_form_words_before_the_strength_are_dropped():
    rows = [{'Generic Name': g, 'Unit Size': '', 'Group Name': 'Anti-Malarial'} for g in
            ('Chloroquine Phosphate Tablets IP 250 mg', 'Arteether Injection 75mg per ml', 'Aciclovir Dispersible Tablets IP 400 mg')]
    assert jan_aushadhi_chunks(rows)[0]['ingredients'] == ['acyclovir', 'arteether', 'chloroquine']
