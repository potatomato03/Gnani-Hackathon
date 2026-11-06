"""Run with VOICERX_TEST_APP_DB=1. Every test rolls its database changes back.

Uses the real approval HTTP route, session/CSRF code, Postgres schema and conversation engine.
The Graph transport and optional model/speech providers are local fakes.
"""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import hmac
import json
import os
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest
from fastapi.testclient import TestClient

from voicerx.app import auth, clinic_reports, followup, followup_routes, journey, main
from voicerx.app.config import load_settings
from voicerx.agent.whatsapp import GraphClient, WhatsAppChannel, WhatsAppConfig
from voicerx.agent.memory import LocalMemoryStore
from voicerx.pipeline.assemble import content_hash

pytestmark = pytest.mark.skipif(os.environ.get('VOICERX_TEST_APP_DB') != '1', reason='opt-in rollback-only database test')


@pytest.fixture
def world(monkeypatch, tmp_path, draft_report):
    settings = replace(load_settings(), artifacts_dir=tmp_path)
    with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=20) as conn:
        with conn.transaction(force_rollback=True):
            @contextmanager
            def transaction():
                with conn.transaction():
                    yield conn
            for module in (main, followup, followup_routes, journey, clinic_reports):
                monkeypatch.setattr(module, 'transaction', transaction)
            suffix = uuid4().hex[:10]
            org, other, doc, patient, encounter = [p + suffix for p in ('org-', 'other-', 'doc-', 'pat-', 'enc-')]
            for oid in (org, other):
                conn.execute('insert into app.organisations(id,name,synthetic) values(%s,%s,true)', (oid, 'Test clinic'))
            conn.execute('insert into app.users(id,display_name,synthetic) values(%s,%s,true)', (doc, 'Dr Synthetic'))
            for oid in (org, other):
                conn.execute("insert into app.memberships values(%s,%s,'doctor')", (doc, oid))
            conn.execute("insert into app.patients(id,organisation_id,mrn,name,sex,birth_year,language_pref,allergy_status,consents,synthetic) "
                         "values(%s,%s,%s,'Synthetic Patient','female',1990,'hi-IN','nka',%s,true)",
                         (patient, org, patient, ['followup_whatsapp']))
            draft = draft_report.model_copy(deep=True)
            draft.header.patient_id = patient
            draft.record_snapshot['patient'].update(patient_id=patient, synthetic=True)
            draft.record_snapshot['clinic']['clinic_id'] = org
            draft.content_hash = content_hash(draft)
            conn.execute("insert into app.encounters(id,organisation_id,patient_id,clinician_id,visit_date,state,current_version) "
                         "values(%s,%s,%s,%s,%s,'in_review',1)", (encounter, org, patient, doc, draft.header.visit_date))
            conn.execute("insert into app.report_versions(encounter_id,version,status,report,content_hash) values(%s,1,'draft',%s,%s)",
                         (encounter, Jsonb(draft.model_dump(mode='json')), draft.content_hash))
            token = auth.create_session(conn, doc, org)
            csrf = auth.load_session(conn, token)['csrf_token']
            service = followup.FollowupService(settings, channel=None, speech=None, nlu=None, reader=None,
                                               memory=LocalMemoryStore(tmp_path / 'memory'))
            monkeypatch.setitem(main.state, 'settings', settings)
            monkeypatch.setitem(main.state, 'followup', service)
            client = TestClient(main.app)
            client.cookies.set(auth.COOKIE, token)
            client.headers['X-CSRF-Token'] = csrf
            response = client.post(f'/api/v1/encounters/{encounter}/approvals', json={
                'expected_version': 1, 'expected_content_hash': draft.content_hash})
            assert response.status_code == 201, response.text
            yield {'conn': conn, 'client': client, 'base': f'/api/v1/encounters/{encounter}/followup',
                   'encounter': encounter, 'patient': patient, 'service': service, 'settings': settings,
                   'org': org, 'other': other, 'doc': doc}
            client.close()


def choose_english(w):
    r = w['client'].post(w['base'] + '/messages', json={'button': 'lang_en-IN'})
    assert r.status_code == 200, r.text
    return r.json()['conversation']


def test_approval_to_patient_reply_to_doctor_task_and_restart(world):
    w = world
    initial = w['client'].get(w['base']).json()
    assert initial['conversation']['language_chosen'] is False
    assert initial['channel'] == 'simulated'
    conv = choose_english(w)
    assert any(m['kind'] == 'summary' for m in conv['messages'])
    approved = w['conn'].execute("select report from app.report_versions where encounter_id=%s and status='approved'",
                                 (w['encounter'],)).fetchone()['report']
    r = w['client'].post(w['base'] + '/messages', json={'text': 'How do I take Dolo?'})
    assert r.status_code == 200
    assert r.json()['conversation']['messages'][-1]['cites'] == ['rx1']
    r = w['client'].post(w['base'] + '/messages', json={'text': 'DOCTOR'})
    task = r.json()['conversation']['tasks'][-1]
    assert task['kind'] == 'callback'
    tasks = w['client'].get('/api/v1/followup/tasks').json()['items']
    assert tasks[0]['encounter_id'] == w['encounter']
    main.state['followup'] = followup.FollowupService(w['settings'], channel=None, speech=None, nlu=None, reader=None,
                                                    memory=w['service'].memory)
    assert w['client'].get(w['base']).json()['conversation']['tasks'][-1]['id'] == task['id']
    assert w['client'].post(w['base'] + f"/tasks/{task['id']}/done").status_code == 200
    assert w['client'].get('/api/v1/followup/tasks').json()['items'] == []
    assert w['conn'].execute("select report from app.report_versions where encounter_id=%s and status='approved'",
                            (w['encounter'],)).fetchone()['report'] == approved


def test_consent_stop_csrf_and_clinic_boundaries(world):
    w = world
    csrf = w['client'].headers.pop('X-CSRF-Token')
    assert w['client'].post(w['base']).status_code == 403
    w['client'].headers['X-CSRF-Token'] = csrf
    assert w['client'].post(w['base'] + '/consent', json={'enabled': False}).status_code == 200
    assert 'consent' in w['client'].get(w['base']).json()['reason']
    assert w['client'].post(w['base'] + '/messages', json={'text': 'DOCTOR'}).status_code == 409
    assert w['client'].post(w['base'] + '/consent', json={'enabled': True}).status_code == 200
    choose_english(w)
    assert w['client'].post(w['base'] + '/messages', json={'text': 'STOP'}).json()['conversation']['stopped']
    assert w['client'].post(w['base']).status_code == 409
    token = auth.create_session(w['conn'], w['doc'], w['other'])
    w['client'].cookies.set(auth.COOKIE, token)
    w['client'].headers['X-CSRF-Token'] = auth.load_session(w['conn'], token)['csrf_token']
    assert w['client'].get(w['base']).status_code == 404
    assert w['client'].get(w['base'] + '/memory').status_code == 404
    assert w['client'].post(w['base'] + '/consent', json={'enabled': True}).status_code == 404
    assert w['client'].get('/api/v1/followup/tasks').json()['items'] == []


def channel_for(w):
    calls = []
    config = WhatsAppConfig(token='fake-token', phone_number_id='fake-business', app_secret='fake-secret',
                            verify_token='fake-verify', test_numbers=frozenset({'910000000001'}))
    def transport(method, url, headers, body):
        calls.append(json.loads(body))
        return 200, {}, json.dumps({'messages': [{'id': f'wamid.fake{len(calls)}'}]}).encode()
    channel = WhatsAppChannel(config, GraphClient(config, transport=transport))
    w['service'].channel = channel
    return channel, calls


def post_event(w, config, message=None, statuses=None, signature=True, phone_id=None):
    value = {'metadata': {'phone_number_id': phone_id or config.phone_number_id}}
    if message:
        value['messages'] = [message]
    if statuses:
        value['statuses'] = statuses
    body = json.dumps({'object': 'whatsapp_business_account', 'entry': [{'changes': [{'value': value}]}]}).encode()
    sig = 'sha256=' + hmac.new(config.app_secret.encode(), body, hashlib.sha256).hexdigest()
    return w['client'].post('/whatsapp/webhook', content=body, headers={
        'Content-Type': 'application/json', 'X-Hub-Signature-256': sig if signature else 'bad'})


def text_event(mid, text):
    return {'id': mid, 'from': '910000000001', 'type': 'text', 'text': {'body': text}}


def test_signed_inbox_one_use_join_deduplication_receipts_and_restart(world):
    w = world
    channel, sent = channel_for(w)
    cfg = channel.config
    invitation = w['client'].post(w['base']).json()['join_command']
    assert post_event(w, cfg, text_event('bad', invitation), signature=False).status_code == 401
    assert post_event(w, cfg, text_event('other', invitation), phone_id='other-business').status_code == 400
    assert post_event(w, cfg, text_event('join', invitation)).status_code == 200
    assert not sent  # request acknowledged only after durable enqueue; worker sends later
    w['service'] = followup.FollowupService(w['settings'], channel=channel, speech=None, nlu=None, reader=None,
                                          memory=w['service'].memory)
    main.state['followup'] = w['service']
    assert w['service'].tick()
    assert sent
    # The JOIN releases the queued visit-complete notice (runbook D-140); let the outbox settle first.
    for _ in range(5):
        if not w['service'].tick():
            break
    before = len(sent)
    post_event(w, cfg, text_event('join', invitation))
    assert w['service'].tick() is False  # duplicate persisted id survives process recreation
    assert len(sent) == before
    row = w['conn'].execute('select * from app.followups where encounter_id=%s', (w['encounter'],)).fetchone()
    assert row['join_hash'] is None
    stored = w['conn'].execute('select payload from app.whatsapp_events').fetchall()
    assert '910000000001' not in json.dumps(stored)
    assert invitation not in json.dumps(stored)
    mid = w['conn'].execute('select message_id from app.whatsapp_receipts where followup_id=%s', (row['id'],)).fetchone()['message_id']
    post_event(w, cfg, statuses=[{'id': mid, 'status': 'delivered'}])
    post_event(w, cfg, statuses=[{'id': mid, 'status': 'sent'}])
    assert w['conn'].execute('select status from app.whatsapp_receipts where message_id=%s', (mid,)).fetchone()['status'] == 'delivered'
    post_event(w, cfg, text_event('reply', 'DOCTOR'))
    assert w['service'].tick()
    assert w['client'].get('/api/v1/followup/tasks').json()['items'][0]['kind'] == 'callback'
    assert w['client'].post(w['base'] + '/messages', json={'text': 'DOCTOR'}).status_code == 409


def test_simulated_checkin_and_urgent_escalation(world):
    w = world
    choose_english(w)
    r = w['client'].post(w['base'] + '/advance')
    assert r.status_code == 200 and r.json()['advanced']
    assert r.json()['conversation']['awaiting']['question'] == 'tolerance'
    r = w['client'].post(w['base'] + '/messages', json={'button': 'no_problem'})
    assert r.status_code == 200
    r = w['client'].post(w['base'] + '/messages', json={'text': 'chest pain'})
    assert r.json()['conversation']['messages'][-1]['kind'] == 'urgent'
    assert w['client'].get('/api/v1/followup/tasks').json()['items'][0]['kind'] == 'urgent'


def test_report_upload_reaches_scoped_doctor_memory_and_stop_prevents_reading(world):
    from voicerx.contracts.documents import ReportFinding, ReportReading
    w = world
    choose_english(w)
    reads = []
    def reader(data, mime):
        reads.append(mime)
        return ReportReading(is_medical_report=True, report_type='Synthetic laboratory report', report_date=None,
                             transcription='Synthetic value 10', medicines_named=[], findings=[
                                 ReportFinding(name='Synthetic value', value='10', unit=None, reference_range=None,
                                               flag=None, quote='Synthetic value 10')]), 'pdf_text', 1
    w['service'].reader = reader
    body = b'%PDF-test-upload-is-memory-only'
    result = w['client'].post(w['base'] + '/documents', content=body, headers={'Content-Type': 'application/pdf'})
    assert result.status_code == 200
    assert result.json()['conversation']['tasks'][-1]['kind'] == 'document'
    memory = w['client'].get(w['base'] + '/memory').json()
    assert memory['documents'][0]['reading']['findings'][0]['value'] == '10'
    assert any(i['kind'] == 'document_fact' for i in memory['items'])
    assert not any(body in p.read_bytes() for p in w['settings'].artifacts_dir.rglob('*') if p.is_file())
    w['client'].post(w['base'] + '/messages', json={'text': 'STOP'})
    assert w['client'].post(w['base'] + '/documents', content=body,
                            headers={'Content-Type': 'application/pdf'}).status_code == 409
    assert reads == ['application/pdf']
