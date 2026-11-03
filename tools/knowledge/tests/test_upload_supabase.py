import numpy
import pytest

from upload_supabase import chunk_rows, label_id, popularity, product_rows, vector_literal


def chunk(id, source='openfda_label', title='Telmisartan', **extra):
    return {'id': id, 'source': source, 'title': title, 'section': 'Uses', 'part': 1, 'parts': 1,
            'ingredients': ['telmisartan'], 'text': 'Telmisartan. Uses: hypertension.', 'url': 'u', 'date': 'd',
            'licence': 'l', **extra}


def test_vector_literal_is_pgvector_text_with_every_dimension():
    text = vector_literal(numpy.array([0.123456, -0.5, 0], dtype=numpy.float32))
    assert text == '[0.12346,-0.50000,0.00000]'


def test_label_id_groups_chunks_of_one_label_medicine_or_group():
    assert label_id(chunk('abc-123:indications_and_usage:2')) == 'abc-123'
    assert label_id(chunk('nlem:telmisartan:1', source='nlem_2022')) == 'nlem:telmisartan'
    assert label_id(chunk('jan_aushadhi:Central Nervous System (CNS):3', source='jan_aushadhi')) == 'jan_aushadhi:Central Nervous System (CNS)'


def test_chunk_rows_pair_each_chunk_with_its_own_vector():
    vectors = numpy.array([[1, 0], [0, 1]], dtype=numpy.float32)
    rows = list(chunk_rows([chunk('b:x:1'), chunk('a:x:1')], ['a:x:1', 'b:x:1'], vectors))
    assert [(r[0], r[-1]) for r in rows] == [('b:x:1', '[0.00000,1.00000]'), ('a:x:1', '[1.00000,0.00000]')]


def test_a_chunk_without_a_vector_stops_the_upload():
    with pytest.raises(KeyError):
        list(chunk_rows([chunk('new:x:1')], ['old:x:1'], numpy.ones((1, 2), dtype=numpy.float32)))


def product(id, name, salt='', short1='', short2='', discontinued='FALSE', kind='allopathy'):
    return {'id': id, 'name': name, 'Is_discontinued': discontinued, 'type': kind, 'manufacturer_name': 'M',
            'pack_size_label': 'strip of 15 tablets', 'salt_composition': salt,
            'short_composition1': short1, 'short_composition2': short2}


def test_products_keep_current_allopathic_rows_with_normalised_ingredients():
    rows = [product('1', 'Dolo 650 Tablet', salt='Paracetamol (650mg)'),
            product('2', 'Old Tablet', salt='Paracetamol (500mg)', discontinued='TRUE'),
            product('3', 'Herbal Syrup', salt='Tulsi', kind='ayurvedic')]
    assert list(product_rows(rows)) == [(1, 'Dolo 650 Tablet', 'M', 'strip of 15 tablets', 'Paracetamol (650mg)', ['acetaminophen'], 1.0)]


def test_most_products_have_only_the_short_composition_columns():
    # 239,220 of 246,068 current products leave salt_composition empty (runbook C-59).
    rows = [product('1', 'Telma 40 Tablet', short1='Telmisartan (40mg) ', short2=''),
            product('2', 'Augmentin 625 Duo Tablet', short1='Amoxycillin  (500mg) ', short2='  Clavulanic Acid (125mg)')]
    assert [(r[4], r[5]) for r in product_rows(rows)] == [
        ('Telmisartan (40mg)', ['telmisartan']),
        ('Amoxycillin (500mg) + Clavulanic Acid (125mg)', ['amoxicillin', 'clavulanic acid'])]


def test_popularity_follows_the_lists_order_within_each_letter():
    # The dataset lists each letter's products best-selling first: PAN 40 2nd and Pan-D 3rd of 9,258 under "P",
    # an obscure sound-alike 1,521st (runbook C-66). The first gets 1, the rest fall off with the log of rank.
    rows = [product('1', 'Primolut-N Tablet'), product('2', 'PAN 40 Tablet'), product('3', 'Augmentin 625 Duo Tablet'),
            product('4', 'Pan-D Capsule PR'), product('5', 'Panday 40mg Tablet')]
    scores = popularity(rows)
    assert scores[1] == scores[3] == 1.0
    assert scores[2] > scores[4] > scores[5] > 0


def test_discontinued_products_keep_their_place_but_get_no_popularity():
    rows = [product('1', 'Old Tablet', discontinued='TRUE'), product('2', 'Ok Tablet')]
    scores = popularity(rows)
    assert scores[1] == 0 and 0 < scores[2] < 1
