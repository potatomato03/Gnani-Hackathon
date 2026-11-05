"""The hospital pharmacy's stock beside the prescription (runbook D-126 to D-128).

A pharmacy exports its stock as CSV (every Indian pharmacy package can); each upload is a full snapshot that
replaces the last. Rows are matched to catalogue products by name and, when given, composition. A row that
names a product the catalogue lacks, with a composition, becomes a clinic product for review.

Stock only informs: it breaks ties between equally close names, labels each prescription line, and offers
in-stock products with the same ingredients, strengths and form. It never changes a line without the doctor's
click, and it ranks by availability only, never by price or margin.
"""
import csv
import io
import re
import uuid
from datetime import datetime, timezone

from ..pipeline.assemble import product_label
from .catalog import FORMS, brand_stem, parse_composition, sound_key, standing
from .suggest import clinic_index, composition_text, entry_form, shared_index

MAX_ROWS = 5000
MAX_BYTES = 2_000_000
# A name alone must sound this close to be taken as the pharmacy's item...
MATCH_SOUND = 0.9
# ...or this close when the row's stated composition agrees exactly with the product's.
MATCH_SOUND_WITH_COMPOSITION = 0.75
# What being in stock adds when ranking: the same as CONFIDENT_MARGIN in suggest.py, so stock only reorders
# names that already sound almost equally close and never lifts a worse-sounding name over a clearly better one.
STOCK_BONUS = 0.05
MAX_ALTERNATIVES = 3
COLUMNS = {
    'item_code': ('item_code', 'code', 'sku', 'item_id', 'id', 'product_code'),
    'item_name': ('item_name', 'name', 'item', 'product', 'product_name', 'medicine', 'description'),
    'composition': ('composition', 'salt', 'generic', 'contents', 'molecule'),
    'quantity': ('quantity', 'qty', 'stock', 'on_hand', 'closing_stock', 'balance', 'available'),
    'reorder_level': ('reorder_level', 'reorder', 'min', 'minimum', 'min_stock', 'reorder_qty'),
}


class StockFileError(ValueError):
    pass


def _column(name):
    return re.sub(r'[^a-z]+', '_', (name or '').strip().lower()).strip('_')


def read_stock_file(text):
    """Rows of {item_code, item_name, composition, quantity, reorder_level} from a stock CSV."""
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise StockFileError('The stock file is larger than 2 MB.')
    reader = csv.reader(io.StringIO(text.lstrip('﻿')))
    header = next(reader, None)
    if not header:
        raise StockFileError('The stock file is empty.')
    names = [_column(h) for h in header]
    where = {}
    for field, aliases in COLUMNS.items():
        where[field] = next((names.index(a) for a in aliases if a in names), None)
    if where['item_name'] is None or where['quantity'] is None:
        raise StockFileError('The stock file needs a name column and a quantity column.')
    rows, codes = [], set()
    for number, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue
        cell = lambda field: values[where[field]].strip() if where[field] is not None and where[field] < len(values) else ''
        name = ' '.join(cell('item_name').split())
        if not name:
            raise StockFileError(f'Row {number} has no item name.')
        try:
            quantity = int(float(cell('quantity') or 0))
            reorder = int(float(cell('reorder_level') or 0))
        except ValueError:
            raise StockFileError(f'Row {number} has a quantity that is not a number.') from None
        code = cell('item_code') or name.lower()
        if code in codes:
            raise StockFileError(f'Row {number} repeats item code {code[:40]}.')
        codes.add(code)
        rows.append({'item_code': code[:80], 'item_name': name[:160], 'composition': ' '.join(cell('composition').split())[:300],
                     'quantity': quantity, 'reorder_level': max(reorder, 0)})
        if len(rows) > MAX_ROWS:
            raise StockFileError(f'The stock file has more than {MAX_ROWS} rows.')
    if not rows:
        raise StockFileError('The stock file has no item rows.')
    return rows


def _strength(value):
    try:
        return f'{float(value):g}'
    except (TypeError, ValueError):
        return (value or '').strip().lower()


def composition_key(text):
    """The same ingredients at the same strengths, however spelt ("Amoxycillin" and "Amoxicillin") or ordered."""
    return frozenset((sound_key(re.sub(r'[^a-z ]+', ' ', c.ingredient.lower()).strip()), _strength(c.strength),
                      (c.unit or '').lower()) for c in parse_composition(text) if c.ingredient)


def _form(name):
    return next((FORMS[w] for w in re.split(r'[^a-z]+', (name or '').lower()) if w in FORMS), None)


def match_item(row, pools):
    """The catalogue entry a pharmacy row is, with its score, or (None, best score)."""
    stated = composition_key(row['composition']) if row['composition'] else None
    form = _form(row['item_name'])
    best, best_rank, best_score = None, -1.0, 0.0
    for pool in pools:
        for candidate in pool.candidates(row['item_name'][:80], limit=8):
            entry = candidate.entry
            agrees = None if not stated else stated == composition_key(entry.composition)
            if agrees is False or candidate.strength_match is False:
                continue
            other = entry_form(entry)
            if form and other and form != other:
                continue
            best_score = max(best_score, candidate.score)
            if candidate.score < (MATCH_SOUND_WITH_COMPOSITION if agrees else MATCH_SOUND):
                continue
            rank = candidate.score + standing(entry) + (0.1 if agrees else 0)
            if rank > best_rank:
                best, best_rank = candidate, rank
    return (best.entry, best.score) if best else (None, best_score)


def _clinic_product(conn, organisation_id, user_id, row):
    """A clinic product for an item the catalogue lacks, made once per name and composition, pending review."""
    found = conn.execute("select id from app.clinic_products where organisation_id = %s and lower(name) = lower(%s) "
                         "and composition = %s and status <> 'withdrawn'",
                         (organisation_id, row['item_name'], row['composition'])).fetchone()
    if found:
        return found['id']
    product_id = 'cp-' + uuid.uuid4().hex[:12]
    conn.execute("insert into app.clinic_products (id, organisation_id, name, form, composition, source, created_by) "
                 "values (%s, %s, %s, %s, %s, 'import', %s)",
                 (product_id, organisation_id, row['item_name'], _form(row['item_name']) or 'other', row['composition'],
                  user_id))
    return product_id


def import_stock(conn, organisation_id, user_id, filename, text, formulary, as_of=None, source='upload'):
    """Replace the hospital's stock with this file's snapshot. Returns the import summary."""
    rows = read_stock_file(text)
    as_of = as_of or datetime.now(timezone.utc)
    pools = [shared_index(conn, formulary), clinic_index(conn, organisation_id)]
    import_id = 'phi-' + uuid.uuid4().hex[:12]
    stocked = []
    for row in rows:
        entry, score = match_item(row, pools)
        if entry:
            product_id, state = entry.id, 'matched'
            label = (product_label(formulary[entry.id]) if entry.id in formulary else entry.name)
            composition, form = entry.composition, entry_form(entry) or _form(row['item_name'])
        elif row['composition'] and all(c.ingredient for c in parse_composition(row['composition'])):
            product_id, state = _clinic_product(conn, organisation_id, user_id, row), 'added'
            label, composition, form = row['item_name'], row['composition'], _form(row['item_name'])
        else:
            product_id, state, label, composition, form = None, 'unmatched', None, row['composition'] or None, None
        stocked.append((organisation_id, row['item_code'], row['item_name'], product_id, label, composition, form, state,
                        round(score, 3) if score else None, row['quantity'], row['reorder_level'], as_of, import_id))
    matched = sum(1 for s in stocked if s[7] != 'unmatched')
    conn.execute('insert into app.pharmacy_imports (id, organisation_id, filename, source, rows, matched, as_of, imported_by) '
                 'values (%s, %s, %s, %s, %s, %s, %s, %s)',
                 (import_id, organisation_id, filename[:120] or 'stock.csv', source, len(rows), matched, as_of, user_id))
    conn.execute('delete from app.pharmacy_stock where organisation_id = %s', (organisation_id,))
    with conn.cursor() as cursor:
        cursor.executemany('insert into app.pharmacy_stock (organisation_id, item_code, item_name, product_id, product_label, '
                           'composition, form, match_state, match_score, quantity, reorder_level, as_of, import_id) '
                           'values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', stocked)
    return summary(conn, organisation_id)


def _brand(label):
    """The brand words of any label: 'PAN 40 TAB (PANTOPRAZOLE) 40MG', 'PAN 40 Tablet' and 'Pan 40' are all 'pan'."""
    return brand_stem(re.sub(r'\([^)]*\)', ' ', label or ''))


def status_of(quantity, reorder_level):
    return 'out' if quantity <= 0 else 'low' if quantity <= reorder_level else 'in_stock'


class Stock:
    """One hospital's current snapshot, grouped by catalogue product (batches of one product add up)."""

    def __init__(self, rows):
        self.as_of = max((r['as_of'] for r in rows), default=None)
        grouped = {}
        for r in rows:
            if not r['product_id']:
                continue
            g = grouped.setdefault(r['product_id'], {'product_id': r['product_id'], 'label': r['product_label'] or r['item_name'],
                                                     'item_name': r['item_name'], 'composition': r['composition'] or '',
                                                     'form': r['form'], 'quantity': 0, 'reorder_level': 0})
            g['quantity'] += r['quantity']
            g['reorder_level'] = max(g['reorder_level'], r['reorder_level'])
        self.items = list(grouped.values())
        self.by_id = grouped
        self.by_identity = {}
        for item in self.items:
            item['status'] = status_of(item['quantity'], item['reorder_level'])
            item['key'] = composition_key(item['composition'])
            self.by_identity.setdefault((_brand(item['label']), item['key']), item)

    def __bool__(self):
        return self.as_of is not None

    def find(self, product_id, label, composition):
        """The stocked item for a product: by id, else the same brand name and composition under another id
        (the formulary's Pan 40 and the Indian list's PAN 40 Tablet)."""
        return self.by_id.get(product_id) or self.by_identity.get((_brand(label), composition_key(composition or '')))

    def bonus(self, entry):
        item = self.find(entry.id, entry.name, entry.composition)
        return STOCK_BONUS if item and item['status'] != 'out' else 0.0

    def badge(self, product_id, label, composition):
        item = self.find(product_id, label, composition)
        return {'status': item['status'], 'quantity': item['quantity']} if item else {'status': 'not_stocked', 'quantity': 0}

    def alternatives(self, product_id, label, composition, form):
        """In-stock products with the same ingredients, strengths and form, most stock first."""
        key = composition_key(composition or '')
        if not key:
            return []
        own = self.find(product_id, label, composition)
        found = [i for i in self.items if i['key'] == key and i is not own and i['status'] != 'out'
                 and not (form and i['form'] and form != i['form'])]
        found.sort(key=lambda i: (i['status'] == 'in_stock', i['quantity']), reverse=True)
        return [{'product_id': i['product_id'], 'label': i['label'], 'composition': i['composition'],
                 'status': i['status'], 'quantity': i['quantity']} for i in found[:MAX_ALTERNATIVES]]

    def line(self, product_id, label, composition, form):
        badge = self.badge(product_id, label, composition)
        offer = badge['status'] in ('out', 'low', 'not_stocked')
        return {**badge, 'alternatives': self.alternatives(product_id, label, composition, form) if offer else []}


def load_stock(conn, organisation_id):
    return Stock(conn.execute('select * from app.pharmacy_stock where organisation_id = %s', (organisation_id,)).fetchall())


def summary(conn, organisation_id):
    """What the pharmacy page shows: the last import, counts, and the rows that need attention."""
    last = conn.execute('select id, filename, rows, matched, as_of, created_at from app.pharmacy_imports '
                        'where organisation_id = %s order by created_at desc limit 1', (organisation_id,)).fetchone()
    if not last:
        return {'imported': False}
    rows = conn.execute('select item_code, item_name, product_id, product_label, composition, match_state, quantity, '
                        'reorder_level from app.pharmacy_stock where organisation_id = %s order by item_name',
                        (organisation_id,)).fetchall()
    items = [{**r, 'status': status_of(r['quantity'], r['reorder_level'])} for r in rows]
    return {'imported': True, 'filename': last['filename'], 'as_of': last['as_of'].isoformat(),
            'imported_at': last['created_at'].isoformat(), 'rows': last['rows'], 'matched': last['matched'],
            'counts': {s: sum(i['status'] == s for i in items) for s in ('in_stock', 'low', 'out')},
            'unmatched': sum(i['match_state'] == 'unmatched' for i in items),
            'added': sum(i['match_state'] == 'added' for i in items), 'items': items}


def annotate_view(view, stock, products):
    """Stock on each prescription line and each suggestion of a report view, plus the snapshot time."""
    if not stock:
        view['pharmacy'] = None
        return view
    view['pharmacy'] = {'as_of': stock.as_of.isoformat()}
    for med in view['medication_views']:
        product = products.get(med.get('product_id')) if med.get('match') == 'exact' else None
        if product and med.get('action') in ('start', 'change', 'continue'):
            med['stock'] = stock.line(product.id, product.brand, composition_text(product), product.form)
        for s in med.get('suggestions', []):
            s['stock'] = stock.badge(s['product_id'], s['label'], s['composition'])
    return view
