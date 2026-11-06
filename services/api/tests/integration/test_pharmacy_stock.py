"""Pharmacy stock end to end with rollback-only synthetic records: upload, labels on the draft, and the swap."""
from uuid import uuid4

from psycopg.types.json import Jsonb

from test_dashboard_followup import world, pytestmark
from voicerx.pipeline.assemble import content_hash

STOCK = ('Item Code,Item Name,Composition,Qty,Reorder Level\n'
         'PH-001,DOLO 650 TAB,Paracetamol (650mg),0,20\n'
         'PH-002,Calpol 650mg Tablet,Paracetamol (650mg),140,20\n'
         'PH-003,Zyxomab Synthetic 10 Tablet,Zyxomab (10mg),12,5\n'
         'PH-004,Mystery item,,3,0\n')


def draft_encounter(w, draft_report):
    draft = draft_report.model_copy(deep=True)
    eid = 'enc-stock-' + uuid4().hex[:10]
    draft.case_id = eid
    draft.header.patient_id = w['patient']
    draft.record_snapshot['patient']['patient_id'] = w['patient']
    draft.record_snapshot['clinic']['clinic_id'] = w['org']
    draft.content_hash = content_hash(draft)
    w['conn'].execute("insert into app.encounters(id,organisation_id,patient_id,clinician_id,visit_date,state,current_version) "
                      "values(%s,%s,%s,%s,%s,'in_review',1)", (eid, w['org'], w['patient'], w['doc'], draft.header.visit_date))
    w['conn'].execute("insert into app.report_versions(encounter_id,version,status,report,content_hash) values(%s,1,'draft',%s,%s)",
                      (eid, Jsonb(draft.model_dump(mode='json')), draft.content_hash))
    return eid, draft


def test_stock_upload_labels_the_draft_and_offers_an_in_stock_swap(world, draft_report, monkeypatch):
    from voicerx.app import pharmacy
    monkeypatch.setattr(pharmacy, 'stock_enabled', lambda: True)  # off by default (runbook D-139)
    w = world
    client = w['client']
    eid, draft = draft_encounter(w, draft_report)
    path = f'/api/v1/encounters/{eid}/report'
    assert client.get(path).json()['pharmacy'] is None
    assert client.get('/api/v1/pharmacy/stock').json() == {'imported': False}

    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/v1/pharmacy/stock', json={'filename': 'stock.csv', 'csv': STOCK}).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    bad = client.post('/api/v1/pharmacy/stock', json={'filename': 'bad.csv', 'csv': 'code,price\nA,1\n'})
    assert bad.status_code == 422 and 'quantity column' in bad.json()['error']['message']

    response = client.post('/api/v1/pharmacy/stock', json={'filename': 'stock.csv', 'csv': STOCK})
    assert response.status_code == 201, response.text
    summary = response.json()
    states = {i['item_code']: i['match_state'] for i in summary['items']}
    assert states == {'PH-001': 'matched', 'PH-002': 'matched', 'PH-003': 'added', 'PH-004': 'unmatched'}
    assert summary['counts'] == {'in_stock': 3, 'low': 0, 'out': 1}
    added = w['conn'].execute("select source, status from app.clinic_products where organisation_id=%s and name=%s",
                              (w['org'], 'Zyxomab Synthetic 10 Tablet')).fetchone()
    assert added == {'source': 'import', 'status': 'pending_review'}

    view = client.get(path).json()
    med = view['medication_views'][0]
    assert view['pharmacy']['as_of'] and med['stock']['status'] == 'out'
    alternative = med['stock']['alternatives'][0]
    assert 'CALPOL' in alternative['label'].upper() and alternative['quantity'] == 140

    swap = client.post(f'/api/v1/encounters/{eid}/resolutions', json={
        'expected_version': 1, 'expected_content_hash': draft.content_hash, 'resolutions': [{
            'action': 'choose_product', 'target': med['id'], 'value': {'product_id': alternative['product_id']},
            'reason': 'Out of stock at the hospital pharmacy; changed to Calpol, same composition.'}]})
    assert swap.status_code == 200, swap.text
    saved = swap.json()
    swapped = saved['medication_views'][0]
    assert saved['version'] == 2 and swapped['product_id'] == alternative['product_id']
    assert swapped['dose'] == med['dose'] and swapped['duration'] == med['duration'] and swapped['schedule'] == med['schedule']
    assert swapped['stock']['status'] == 'in_stock' and swapped['stock']['alternatives'] == []
    assert w['doc'] in saved['report']['resolutions'][-1]['by']

    other = w['conn'].execute('select count(*) as n from app.pharmacy_stock where organisation_id=%s', (w['other'],)).fetchone()
    assert other['n'] == 0
    audit = w['conn'].execute("select detail from app.audit_events where organisation_id=%s and action='pharmacy.stock_imported'",
                              (w['org'],)).fetchone()
    assert audit['detail']['rows'] == 4


def test_with_stock_switched_off_nothing_shows_and_the_page_is_closed(world, draft_report, monkeypatch):
    from voicerx.app import pharmacy
    monkeypatch.setattr(pharmacy, 'stock_enabled', lambda: False)
    w = world
    client = w['client']
    eid, _ = draft_encounter(w, draft_report)
    assert client.get('/api/v1/me').json()['capabilities']['pharmacy'] is False
    assert client.post('/api/v1/pharmacy/stock', json={'filename': 'stock.csv', 'csv': STOCK}).status_code == 403
    assert client.get(f'/api/v1/encounters/{eid}/report').json()['pharmacy'] is None
