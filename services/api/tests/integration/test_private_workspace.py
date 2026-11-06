"""Rollback-only access, registration and per-report patient context checks."""
from uuid import uuid4
from dataclasses import replace

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from test_dashboard_followup import world,channel_for,post_event,text_event,pytestmark
from test_patient_journey import next_visit,store_pdf
from test_clinic_report_delivery import Speech
from voicerx.app import auth,main,workspace,audio_uploads
from voicerx.app.private_access import password_hash,decrypt_phone,encrypt_phone
from voicerx.app.clinic_reports import MENU_PREFIX
import pytest


def private_world(w,monkeypatch):
    monkeypatch.setattr(workspace,'transaction',main.transaction)
    monkeypatch.setattr(audio_uploads,'transaction',main.transaction)
    w['conn'].execute('update app.users set workspace_admin=true where id=%s',(w['doc'],))
    username='private-'+uuid4().hex[:10];password='A private demo password 42!'
    w['conn'].execute('insert into app.login_accounts(username,user_id,password_hash) values(%s,%s,%s)',
                      (username,w['doc'],password_hash(password)))
    token=auth.create_session(w['conn'],w['doc'],w['org'],operator_id=w['doc'])
    w['client'].cookies.set(auth.COOKIE,token)
    w['client'].headers['X-CSRF-Token']=auth.load_session(w['conn'],token)['csrf_token']
    return username,password


def test_unauthenticated_link_reveals_only_generic_login_and_blocks_product_assets(world,monkeypatch):
    w=world;private_world(w,monkeypatch)
    monkeypatch.setattr(main,'state',{**main.state,'settings':replace(w['settings'],dev_login=False)})
    client=TestClient(main.app)
    root=client.get('/')
    # The sign-in page (runbook D-129) shows the product pitch but no app code and no patient data.
    assert root.status_code==200 and 'id="loginForm"' in root.text and 'no-store' in root.headers['cache-control']
    assert '/static/' not in root.text and 'Synthetic Patient' not in root.text
    for path in ('/static/app.js','/static/app.css','/static/app_v2/app.css','/api/v1/patients','/api/v1/workspace/hospitals','/v1'):
        response=client.get(path)
        assert response.status_code==401,(path,response.text)
        assert 'no-store' in response.headers['cache-control']
    assert client.get('/api/v1/auth/dev-users').status_code==404
    assert client.post('/api/v1/auth/dev-login',json={'user_id':w['doc']}).status_code==404
    assert client.get('/openapi.json').status_code==404
    for name in ('login.js','login.css','base.css'):
        assert client.get('/auth-assets/'+name).status_code==200
    assert client.get('/auth-assets/app.js').status_code==404


def test_password_login_origin_csrf_logout_and_persisted_limits(world,monkeypatch):
    w=world;username,password=private_world(w,monkeypatch);client=TestClient(main.app)
    assert client.post('/api/v1/auth/login',json={'username':username,'password':password},headers={'Origin':'https://foreign.example'}).status_code==403
    response=client.post('/api/v1/auth/login',json={'username':username,'password':password})
    assert response.status_code==200 and response.json()['workspace_admin']
    cookie=response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie
    assert 'max-age' not in cookie and 'expires' not in cookie  # ends with the browser (runbook D-134)
    assert client.get('/api/v1/me').status_code==200
    assert client.post('/api/v1/auth/logout').status_code==403
    assert client.post('/api/v1/auth/logout',headers={'X-CSRF-Token':response.json()['csrf_token']}).status_code==204
    assert client.get('/api/v1/me').status_code==401
    for _ in range(8):
        assert client.post('/api/v1/auth/login',json={'username':username,'password':'Wrong demo password 123!'}).status_code==401
    assert client.post('/api/v1/auth/login',json={'username':username,'password':password}).status_code==429


def test_private_request_checks_session_once_and_next_request_still_checks_revocation(world,monkeypatch):
    w=world;private_world(w,monkeypatch)
    original=auth.load_session;checks=[]
    def counted(conn,token):
        checks.append(True)
        return original(conn,token)
    monkeypatch.setattr(auth,'load_session',counted)
    assert w['client'].get('/api/v1/me').status_code==200
    assert len(checks)==1
    auth.end_session(w['conn'],w['client'].cookies.get(auth.COOKIE))
    assert w['client'].get('/api/v1/me').status_code==401
    assert len(checks)==2


def test_hierarchy_onboarding_registration_encryption_and_hospital_boundaries(world,monkeypatch):
    w=world;private_world(w,monkeypatch);channel,calls=channel_for(w)
    hospitals=w['client'].get('/api/v1/workspace/hospitals').json()['items']
    assert {row['id'] for row in hospitals}=={w['org'],w['other']}
    path=f"/api/v1/workspace/hospitals/{w['org']}/doctors"
    doctor=w['client'].post(path,json={'name':'Dr Test Onboarding','specialty':'General Medicine'})
    assert doctor.status_code==201
    did=doctor.json()['id']
    body={'name':'New Test Patient','phone':'910000000001','language':'hi-IN','doctor_id':did,'birth_year':1990,'sex':'F',
          'ai_consent':True,'whatsapp_consent':True,'recording_consent':True}
    response=w['client'].post('/api/v1/patients',json=body)
    assert response.status_code==201,response.text
    pid=response.json()['patient']['id']
    row=w['conn'].execute('select * from app.patients where id=%s',(pid,)).fetchone()
    assert row['phone'] is None and row['phone_encrypted']!=body['phone']
    assert decrypt_phone(row['phone_encrypted'])==body['phone']
    assert body['phone'] not in response.text and 'phone_encrypted' not in response.text
    assert row['phone_last4']=='0001' and row['assigned_doctor_id']==did
    assert 'followup_whatsapp' in row['consents']
    listed=w['client'].get('/api/v1/patients',params={'doctor_id':did}).json()['items']
    assert [p['id'] for p in listed]==[pid]
    assert w['client'].post('/api/v1/patients',json={**body,'phone':'910000000009'}).status_code==422
    assert w['client'].post('/api/v1/patients',json={**body,'ai_consent':False}).status_code==422
    foreign='not-a-member-'+uuid4().hex
    w['conn'].execute('insert into app.organisations(id,name,synthetic) values(%s,%s,true)',(foreign,'Other private hospital'))
    assert w['client'].get(f'/api/v1/workspace/hospitals/{foreign}/doctors').status_code==404
    assert w['client'].post('/api/v1/workspace/select',json={'hospital_id':foreign}).status_code==404
    selected=w['client'].post('/api/v1/workspace/select',json={'hospital_id':w['other']})
    assert selected.status_code==200
    assert 'max-age' not in selected.headers['set-cookie'].lower()
    assert selected.json()['workspace']['hospital']['id']==w['other']
    assert all(item['id']==w['doc'] for item in selected.json()['workspace']['items'])
    w['client'].headers['X-CSRF-Token']=selected.json()['csrf_token']
    assert w['client'].get('/api/v1/patients/'+pid).status_code==404
    assert w['client'].post('/api/v1/patients',json=body).status_code==422
    assert w['client'].post('/api/v1/workspace/select',json={'hospital_id':w['other'],'doctor_id':did}).status_code==404


def test_registered_patient_approval_delivers_to_entered_number_and_report_menu_routes_history(world,monkeypatch):
    w=world;private_world(w,monkeypatch);channel,calls=channel_for(w)
    service=w['service'];service.speech=Speech();service.clinic_reports.target=None
    monkeypatch.setattr(channel.graph,'upload_document',lambda data,name:'test-pdf-media')
    monkeypatch.setattr(channel.graph,'upload_audio',lambda data,mime:'test-audio-media')
    contact=channel.contact('910000000001')
    w['conn'].execute('update app.patients set phone_encrypted=%s,phone_last4=%s where id=%s',
                      (encrypt_phone('910000000001'),'0001',w['patient']))
    w['conn'].execute('insert into app.patient_contact_requests(patient_id,organisation_id,expected_contact) values(%s,%s,%s)',
                      (w['patient'],w['org'],contact))
    w['conn'].execute('insert into app.whatsapp_contact_windows(contact,last_inbound_at) values(%s,now())',(contact,))
    eid=next_visit(w);store_pdf(w,eid)
    jobs=w['conn'].execute('select * from app.clinic_report_jobs where encounter_id=%s',(eid,)).fetchall()
    assert {job['kind'] for job in jobs}=={'visit_complete','report_pdf','voice_option'}
    assert all(job['delivery_mode']=='patient' and job['recipient']==contact for job in jobs)
    assert not w['conn'].execute('select d.id from app.patient_deliveries d join app.followups f on f.id=d.followup_id '
                                'where f.encounter_id=%s',(eid,)).fetchall()
    for _ in range(3):assert service.clinic_reports.tick()
    assert [call['type'] for call in calls]==['text','document','interactive']
    assert 'is complete' in calls[0]['text']['body']
    assert not service.speech.requests
    pdf=next(job for job in jobs if job['kind']=='report_pdf')
    buttons=calls[-1]['interactive']['action']['buttons']
    assert {b['reply']['title'] for b in buttons}=={'Prescription voice','Patient menu'}
    event={'id':'private-menu','from':'910000000001','type':'interactive',
           'interactive':{'type':'button_reply','button_reply':{'id':MENU_PREFIX+pdf['id'],'title':'Patient menu'}}}
    post_event(w,channel.config,event);assert service.tick()
    active=w['conn'].execute('select a.*,f.encounter_id from app.whatsapp_active_reports a join app.followups f on f.id=a.followup_id '
                             'where contact=%s',(contact,)).fetchone()
    assert active['encounter_id']==eid
    # A different allowlisted phone cannot select this patient's report.
    channel.config=replace(channel.config,test_numbers=frozenset({'910000000001','910000000002'}))
    post_event(w,channel.config,{**event,'id':'other-private-menu','from':'910000000002'});assert service.tick()
    assert not w['conn'].execute('select * from app.whatsapp_active_reports where contact=%s',(channel.contact('910000000002'),)).fetchone()
    post_event(w,channel.config,text_event('private-med-question','How do I take Dolo?'));assert service.tick()
    conv=w['conn'].execute('select conversation from app.followups where id=%s',(active['followup_id'],)).fetchone()['conversation']
    assert conv['records'][-1]['raw_text']=='How do I take Dolo?'
    assert not w['conn'].execute('select patient_id from app.patient_channels where patient_id=%s',(w['patient'],)).fetchone()
    post_event(w,channel.config,{'id':'private-stop-menu','from':'910000000001','type':'interactive',
                               'interactive':{'type':'button_reply','button_reply':{'id':'menu_stop','title':'Stop follow-up'}}})
    assert service.tick()
    post_event(w,channel.config,{'id':'private-stop-button','from':'910000000001','type':'interactive',
                               'interactive':{'type':'button_reply','button_reply':{'id':'stop_yes','title':'Stop'}}})
    assert service.tick()
    assert w['conn'].execute('select opted_out_at from app.whatsapp_contact_windows where contact=%s',(contact,)).fetchone()['opted_out_at']


def test_chunked_recording_is_scoped_idempotent_and_survives_a_missing_local_file(world,monkeypatch):
    import io,wave
    from hashlib import sha256
    w=world;private_world(w,monkeypatch)
    # A new unprocessed visit; no model or speech API is called by upload.
    eid='audio-private-'+uuid4().hex[:12]
    w['conn'].execute("insert into app.encounters(id,organisation_id,patient_id,clinician_id,visit_date) values(%s,%s,%s,%s,current_date)",
                      (eid,w['org'],w['patient'],w['doc']))
    w['conn'].execute("update app.patients set consents=array_append(consents,'recording') where id=%s",(w['patient'],))
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as audio:
        audio.setnchannels(2);audio.setsampwidth(2);audio.setframerate(48000);audio.writeframes(bytes(18*48000*4))
    data=buffer.getvalue()
    response=w['client'].post(f'/api/v1/encounters/{eid}/audio-uploads',json={
        'size':len(data),'media_type':'audio/wav','language':'english','recording_consent':True})
    assert response.status_code==201,response.text
    upload=response.json();base='/api/v1/audio-uploads/'+upload['id']
    assert w['client'].post(base+'/complete').status_code==422
    other=TestClient(main.app);token=auth.create_session(w['conn'],w['doc'],w['other'])
    other.cookies.set(auth.COOKIE,token);other.headers['X-CSRF-Token']=auth.load_session(w['conn'],token)['csrf_token']
    assert other.put(base+'/parts/0',content=data[:upload['part_bytes']]).status_code==404
    for part,offset in enumerate(range(0,len(data),upload['part_bytes'])):
        response=w['client'].put(base+f'/parts/{part}',content=data[offset:offset+upload['part_bytes']])
        assert response.status_code==200,response.text
    first=w['client'].post(base+'/complete');assert first.status_code==200,first.text
    again=w['client'].post(base+'/complete');assert again.status_code==200 and again.json()['id']==first.json()['id']
    sid=first.json()['id'];saved=w['conn'].execute('select * from app.source_files where source_id=%s',(sid,)).fetchone()
    assert saved['sha256']==sha256(data).hexdigest() and bytes(saved['data'])==data
    source=w['conn'].execute('select * from app.sources where id=%s',(sid,)).fetchone()
    local=w['settings'].artifacts_dir/eid/'sources'/source['file_name'];local.unlink()
    response=w['client'].get(f'/api/v1/encounters/{eid}/sources/{sid}/audio')
    assert response.status_code==200 and response.content==data
    assert other.get(f'/api/v1/encounters/{eid}/sources/{sid}/audio').status_code==404


@pytest.mark.parametrize('number',['910000000001','910000000002'])
def test_each_permitted_phone_receives_only_its_registered_patient_report_and_voice(world,monkeypatch,number):
    w=world;private_world(w,monkeypatch);channel,calls=channel_for(w)
    channel.config=replace(channel.config,test_numbers=frozenset({'910000000001','910000000002'}))
    service=w['service'];service.speech=Speech();service.clinic_reports.target=None
    monkeypatch.setattr(channel.graph,'upload_document',lambda data,name:'test-pdf-media')
    monkeypatch.setattr(channel.graph,'upload_audio',lambda data,mime:'test-audio-media')
    contact=channel.contact(number)
    w['conn'].execute('update app.patients set phone_encrypted=%s where id=%s',(encrypt_phone(number),w['patient']))
    w['conn'].execute('insert into app.patient_contact_requests(patient_id,organisation_id,expected_contact) values(%s,%s,%s)',
                      (w['patient'],w['org'],contact))
    w['conn'].execute('insert into app.whatsapp_contact_windows(contact,last_inbound_at) values(%s,now())',(contact,))
    eid=next_visit(w);store_pdf(w,eid)
    for _ in range(3):assert service.clinic_reports.tick()
    assert [call['type'] for call in calls]==['text','document','interactive']
    assert all(call['to']==number for call in calls) and not service.speech.requests
    pdf=w['conn'].execute("select * from app.clinic_report_jobs where encounter_id=%s and kind='report_pdf'",(eid,)).fetchone()
    other=next(candidate for candidate in channel.config.test_numbers if candidate!=number)
    def event(mid,sender):
        return {'id':mid,'from':sender,'type':'interactive','interactive':{'type':'button_reply',
                'button_reply':{'id':'report_voice:'+pdf['id'],'title':'Prescription voice'}}}
    post_event(w,channel.config,event('wrong-recipient-'+number,other));assert service.tick()
    assert not w['conn'].execute("select id from app.clinic_report_jobs where source_job=%s and kind='prescription_voice'",(pdf['id'],)).fetchone()
    post_event(w,channel.config,event('correct-recipient-'+number,number));assert service.tick()
    assert service.clinic_reports.tick()
    assert calls[-1]['type']=='audio' and calls[-1]['to']==number
