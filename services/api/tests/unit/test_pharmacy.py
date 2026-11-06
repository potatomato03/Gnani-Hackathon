"""Hospital pharmacy stock: reading the export, matching items, and what each line shows (runbook D-126)."""
from datetime import datetime, timezone

import pytest

from voicerx.app.catalog import CatalogEntry, NameIndex
from voicerx.app.pharmacy import (STOCK_BONUS, Stock, StockFileError, annotate_view, composition_key, match_item,
                                  read_stock_file, status_of)

AS_OF = datetime(2026, 11, 5, 10, 40, tzinfo=timezone.utc)


def row(code, product_id, label, composition, quantity, reorder=0, form='tablet'):
    return {'item_code': code, 'item_name': label, 'product_id': product_id, 'product_label': label,
            'composition': composition, 'form': form, 'quantity': quantity, 'reorder_level': reorder, 'as_of': AS_OF}


def test_reads_common_export_headers_and_skips_blank_rows():
    rows = read_stock_file('﻿SKU,Product Name,Salt,Closing Stock,Min Stock\n'
                           'A1,PAN 40 TAB,Pantoprazole (40mg),12,20\n\n'
                           'A2,Dolo 650 Tablet,,0,\n')
    assert rows == [
        {'item_code': 'A1', 'item_name': 'PAN 40 TAB', 'composition': 'Pantoprazole (40mg)', 'quantity': 12, 'reorder_level': 20},
        {'item_code': 'A2', 'item_name': 'Dolo 650 Tablet', 'composition': '', 'quantity': 0, 'reorder_level': 0}]


@pytest.mark.parametrize('text, message', [
    ('', 'empty'),
    ('code,price\nA1,10\n', 'name column and a quantity column'),
    ('name,qty\nDolo 650,many\n', 'not a number'),
    ('code,name,qty\nA1,Dolo,1\nA1,Pan,2\n', 'repeats item code'),
    ('name,qty\n', 'no item rows'),
])
def test_refuses_files_it_cannot_read_safely(text, message):
    with pytest.raises(StockFileError, match=message):
        read_stock_file(text)


def test_composition_key_ignores_order_spelling_and_trailing_zeros():
    assert composition_key('Amoxycillin (500mg) + Clavulanic Acid (125mg)') == \
        composition_key('Clavulanic Acid (125.0mg) + Amoxicillin (500mg)')
    assert composition_key('Pantoprazole (40mg)') != composition_key('Pantoprazole (20mg)')


def test_status_follows_quantity_and_reorder_level():
    assert [status_of(0, 5), status_of(5, 5), status_of(6, 5), status_of(-2, 0)] == ['out', 'low', 'in_stock', 'out']


def index(*entries):
    return NameIndex([CatalogEntry(*e) for e in entries])


def test_matches_a_pharmacy_item_by_name_and_refuses_another_strength_or_composition():
    pool = index(('p-pan-40', 'Pan 40 tablet', 'Pantoprazole (40mg)', 'formulary'),
                 ('in-1', 'PAN 20 Tablet', 'Pantoprazole (20mg)', 'indian'),
                 ('in-2', 'Pan-D Capsule', 'Domperidone (30mg) + Pantoprazole (40mg)', 'indian'))
    entry, _ = match_item({'item_name': 'PAN 40 TAB', 'composition': ''}, [pool])
    assert entry.id == 'p-pan-40'
    entry, _ = match_item({'item_name': 'PAN 40 TAB', 'composition': 'Pantoprazole (20mg)'}, [pool])
    assert entry is None
    entry, _ = match_item({'item_name': 'Zyxomab 10 Tablet', 'composition': ''}, [pool])
    assert entry is None


def test_a_stated_composition_lets_a_less_exact_name_match():
    pool = index(('in-9', 'Pantocid Tablet', 'Pantoprazole (40mg)', 'indian'))
    entry, score = match_item({'item_name': 'PANTOCID TAB', 'composition': 'Pantoprazole (40mg)'}, [pool])
    assert entry.id == 'in-9' and score >= 0.75


def stock():
    return Stock([row('A1', 'p-pan-40', 'PAN 40 TAB (PANTOPRAZOLE) 40MG', 'Pantoprazole (40mg)', 0, 10),
                  row('A2', 'in-173581', 'Pantop 40 Tablet', 'Pantoprazole (40mg)', 30, 10),
                  row('A3', 'in-173591', 'Pantocid Tablet', 'Pantoprazole (40mg)', 8, 10),
                  row('A4', 'in-55', 'Pantodac Injection', 'Pantoprazole (40mg)', 50, 0, form='injection'),
                  row('A5', 'in-58235', 'Dolo 650 Tablet', 'Paracetamol (650mg)', 4, 0),
                  row('A6', 'in-58235', 'Dolo 650 Tablet', 'Paracetamol (650mg)', 6, 0),
                  {**row('A7', None, 'Unknown item', '', 9), 'product_id': None}])


def test_out_of_stock_line_offers_same_composition_and_form_most_stock_first():
    line = stock().line('p-pan-40', 'Pan 40', 'Pantoprazole (40mg)', 'tablet')
    assert line['status'] == 'out' and line['quantity'] == 0
    assert [a['product_id'] for a in line['alternatives']] == ['in-173581', 'in-173591']
    assert line['alternatives'][1]['status'] == 'low'


def test_finds_the_same_product_under_another_catalogue_id_and_adds_batches():
    s = stock()
    assert s.badge('in-173578', 'PAN 40 Tablet', 'Pantoprazole (40mg)') == {'status': 'out', 'quantity': 0}
    assert s.badge('p-dolo-650', 'DOLO 650 TAB (PARACETAMOL) 650MG', 'Paracetamol (650mg)') == {'status': 'in_stock', 'quantity': 10}
    assert s.badge('p-telma-40', 'Telma 40', 'Telmisartan (40mg)') == {'status': 'not_stocked', 'quantity': 0}


def test_in_stock_line_offers_nothing_and_stock_bonus_skips_out_of_stock():
    s = stock()
    assert s.line('in-173581', 'Pantop 40', 'Pantoprazole (40mg)', 'tablet')['alternatives'] == []
    assert s.bonus(CatalogEntry('in-173581', 'Pantop 40 Tablet', 'Pantoprazole (40mg)', 'indian')) == STOCK_BONUS
    assert s.bonus(CatalogEntry('p-pan-40', 'Pan 40 tablet', 'Pantoprazole (40mg)', 'formulary')) == 0.0


def test_no_snapshot_means_no_stock_shown():
    view = {'medication_views': []}
    assert not Stock([])
    assert annotate_view(view, Stock([]), {})['pharmacy'] is None


def test_annotates_prescribed_lines_and_suggestions_only(approved_report):
    report = approved_report
    rx = report.checked.medications[0]
    products = dict(report.products_used)
    view = {'medication_views': [{**rx.model_dump(mode='json'), 'suggestions': [
        {'product_id': 'in-173581', 'label': 'PANTOP 40 TAB (PANTOPRAZOLE) 40MG', 'composition': 'Pantoprazole (40mg)'}]}]}
    annotate_view(view, stock(), products)
    med = view['medication_views'][0]
    assert view['pharmacy']['as_of'] == AS_OF.isoformat()
    assert med['stock']['status'] == 'in_stock' and med['stock']['quantity'] == 10
    assert med['suggestions'][0]['stock'] == {'status': 'in_stock', 'quantity': 30}


def test_stock_is_off_unless_switched_on(monkeypatch):
    from voicerx.app import pharmacy

    class NoQueries:
        def execute(self, *args):
            raise AssertionError('stock read while switched off')
    monkeypatch.delenv('APP_PHARMACY_STOCK', raising=False)
    monkeypatch.setattr(pharmacy, 'stock_enabled', lambda: False)
    assert not pharmacy.load_stock(NoQueries(), 'org-1')
