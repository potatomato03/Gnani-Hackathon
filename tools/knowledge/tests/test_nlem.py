from nlem import nlem_chunks, nlem_ingredients, parse_nlem


def test_ingredients_skip_labels_and_brackets():
    assert nlem_ingredients('Co-trimoxazole [Sulphamethoxazole (A) + Trimethoprim (B)]') == ['sulfamethoxazole', 'trimethoprim']
    assert nlem_ingredients('Ascorbic acid (Vitamin C)') == ['ascorbic acid']
    assert nlem_ingredients('Amoxicillin (A) + Clavulanic acid (B)') == ['amoxicillin', 'clavulanic acid']

PAGES = [
    """Section 2
Analgesics and Antipyretics
2.3-Medicines used to treat Gout
 Medicine Level of Healthcare Dosage form(s) and strength(s)
2.3.1 Allopurinol*** P,S,T Tablet 100 mg Tablet 300 mg
2.3.2 Colchicine P,S,T Tablet 0.5 mg
*** Allopurinol formulations are also listed in
Section 7.4.1 - Allopurinol formulations are also listed in Anti-cancer agents
Palliative Care
""",
    """Section 6
Anti-infective Medicines
6.2-Antibacterials
6.2.1  Beta-lactam Medicines
  Medicine Level of Healthcare Dosage form(s) and strength(s)
6.2.1.2 Amoxicillin (A) + Clavulanic acid (B)
P,S,T
Tablet 500 mg (A) + 125 mg (B)
Section 7
Anti-cancer agents
7.4.1 Allopurinol T Tablet 100 mg
""",
]


def test_medicines_carry_their_category_level_and_forms():
    medicines = parse_nlem(PAGES)
    allopurinol = medicines['Allopurinol']
    assert allopurinol['categories'] == ['Analgesics and Antipyretics > Medicines used to treat Gout', 'Anti-cancer agents']
    assert allopurinol['levels'] == ['P,S,T', 'T']
    assert 'Tablet 300 mg' in allopurinol['forms'][0]
    assert medicines['Colchicine']['forms'] == ['Tablet 0.5 mg']


def test_footnotes_are_not_medicines_or_headings():
    medicines = parse_nlem(PAGES)
    assert set(medicines) == {'Allopurinol', 'Colchicine', 'Amoxicillin (A) + Clavulanic acid (B)'}
    assert all('also listed' not in f for m in medicines.values() for f in m['forms'])


def test_level_on_its_own_line_and_nested_headings():
    combination = parse_nlem(PAGES)['Amoxicillin (A) + Clavulanic acid (B)']
    assert combination['categories'] == ['Anti-infective Medicines > Antibacterials > Beta-lactam Medicines']
    assert combination['levels'] == ['P,S,T'] and combination['forms'] == ['Tablet 500 mg (A) + 125 mg (B)']


def test_bare_numbers_multiline_names_and_wrapped_headings():
    page = """Section 18
Hormones
18.3-Medicines used in Diabetes Mellitus and Non-
steroidal things
 Medicine Level of Healthcare Dosage form(s) and strength(s)
18.3.1.3 Insulin
Intermediate
Acting (NPH)
P,S,T Injection 40 IU/mL
18.3.1.5
Insulin Premix
P,S,T Injection 40 IU/mL
18.3.1.6 Metformin P,S,T
Tablet 500 mg
"""
    medicines = parse_nlem([page])
    assert set(medicines) == {'Insulin Intermediate Acting (NPH)', 'Insulin Premix', 'Metformin'}
    assert medicines['Metformin']['categories'] == ['Hormones > Medicines used in Diabetes Mellitus and Non-steroidal things']
    assert medicines['Insulin Premix']['forms'] == ['Injection 40 IU/mL']


def test_table_header_on_the_heading_line_and_scope_notes_are_dropped():
    page = """Section 14
Antiseptics and Disinfectants
14.1 Antiseptics  Medicine  Level of Healthcare Dosage form(s) and strength(s)
14.1.1 Povidone iodine P,S,T Solution 5%
Section 19
Immunologicals
19.4 Vaccines a) All the vaccines which are under Universal Immunization Program
19.4.1 BCG vaccine P,S,T Injection
Section 17
Gastrointestinal Medicines
17.7  Other medicines
 Medicine
Level of
Healthcare Dosage form(s) and strength(s)
17.7.1 Somatostatin T Powder for Injection 3 mg
"""
    medicines = parse_nlem([page])
    assert medicines['Povidone iodine']['categories'] == ['Antiseptics and Disinfectants > Antiseptics']
    assert medicines['BCG vaccine']['categories'] == ['Immunologicals > Vaccines']
    assert medicines['Somatostatin']['categories'] == ['Gastrointestinal Medicines > Other medicines']


def test_one_medicine_spelled_two_ways_is_one_entry():
    page = """Section 6
Anti-infective Medicines
6.2.2.3 Doxycycline P,S,T Capsule 100 mg
6.3.1 Doxycycline** # P,S,T Tablet 100 mg
Section 5
Neurological
5.1.9 Sodium Valproate P,S,T Tablet 200 mg
5.1.10 Sodium valproate P,S,T Injection 100 mg/mL
"""
    medicines = parse_nlem([page])
    assert set(medicines) == {'Doxycycline', 'Sodium Valproate'}
    assert medicines['Doxycycline']['forms'] == ['Capsule 100 mg', 'Tablet 100 mg']


def test_chunk_ids_stay_unique_when_two_listings_share_an_ingredient():
    entry = {'categories': ['Dermatological'], 'levels': ['P,S,T'], 'forms': ['Cream 0.05%']}
    chunks = nlem_chunks({'Betamethasone': entry, 'Betamethasone dipropionate': entry})
    assert [c['id'] for c in chunks] == ['nlem:betamethasone:1', 'nlem:betamethasone-dipropionate:1']


def test_one_chunk_per_medicine_explains_the_levels():
    chunk = next(c for c in nlem_chunks(parse_nlem(PAGES)) if c['title'] == 'Colchicine')
    assert chunk['ingredients'] == ['colchicine'] and chunk['source'] == 'nlem_2022'
    assert chunk['text'].startswith('Colchicine is on India\'s National List of Essential Medicines 2022')
    assert 'Medicines used to treat Gout' in chunk['text'] and 'P = primary' in chunk['text']
