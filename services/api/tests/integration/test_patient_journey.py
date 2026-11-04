from datetime import date
from hashlib import sha256
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from test_dashboard_followup import world, choose_english, channel_for, post_event, text_event, pytestmark
from voicerx.contracts.report import DraftReport
from voicerx.pipeline.assemble import content_hash


def next_visit(w):
    current=w['conn'].execute("select report from app.report_versions where encounter_id=%s and status='approved'",(w['encounter'],)).fetchone()['report']
    data={k:v for k,v in current.items() if k not in ('approved_by','approved_at')}
    eid='enc-next-'+uuid4().hex[:10];data['case_id']=eid;data['status']='draft';data['header']['visit_date']=date.today().isoformat()
    draft=DraftReport.model_validate(data);draft.content_hash=content_hash(draft)
    w['conn'].execute("insert into app.encounters(id,organisation_id,patient_id,clinician_id,visit_date,state,current_version) values(%s,%s,%s,%s,%s,'in_review',1)",
                      (eid,w['org'],w['patient'],w['doc'],draft.header.visit_date))
    w['conn'].execute("insert into app.report_versions(encounter_id,version,status,report,content_hash) values(%s,1,'draft',%s,%s)",
                      (eid,Jsonb(draft.model_dump(mode='json')),draft.content_hash))
    r=w['client'].post(f'/api/v1/encounters/{eid}/approvals',json={'expected_version':1,'expected_content_hash':draft.content_hash})
    assert r.status_code==201,r.text
    return eid


def connect(w):
    channel,calls=channel_for(w)
    command=w['client'].post(w['base']).json()['join_command']
    assert post_event(w,channel.config,text_event('join-'+uuid4().hex,command)).status_code==200
    assert w['service'].tick()
    return channel,calls


def store_pdf(w,eid):
    data=b'%PDF-1.4 synthetic archived approved PDF'
    w['conn'].execute('insert into app.report_files(encounter_id,version,sha256,data) values(%s,1,%s,%s)',
                      (eid,sha256(data).hexdigest(),data))
    return data


def test_approval_queues_only_pdf_and_never_automatic_audio(world):
    w=world
    jobs=w['conn'].execute('select kind from app.patient_deliveries d join app.followups f on f.id=d.followup_id where f.encounter_id=%s',
                           (w['encounter'],)).fetchall()
    assert [j['kind'] for j in jobs]==['report_pdf']


def test_verified_patient_link_carries_into_next_visit_and_automatically_delivers_pdf(world,monkeypatch):
    w=world;channel,calls=connect(w)
    eid=next_visit(w);expected=store_pdf(w,eid)
    uploaded=[]
    monkeypatch.setattr(channel.graph,'upload_document',lambda data,name:uploaded.append((data,name)) or 'media-pdf')
    for _ in range(4):w['service'].journey.tick()
    row=w['conn'].execute("select d.* from app.patient_deliveries d join app.followups f on f.id=d.followup_id where f.encounter_id=%s",(eid,)).fetchone()
    assert row['state']=='accepted'
    assert uploaded[0][0]==expected
    assert any(call.get('type')=='document' for call in calls)
    assert not any(call.get('type')=='audio' for call in calls)
    r=w['client'].get(f'/api/v1/encounters/{eid}/followup').json()
    assert r['channel']=='whatsapp' and r['conversation']['contact']
    assert w['conn'].execute('select conversation from app.followups where encounter_id=%s',(w['encounter'],)).fetchone()['conversation']['superseded']
    post_event(w,channel.config,statuses=[{'id':row['provider_id'],'status':'read'}])
    assert w['conn'].execute('select state from app.patient_deliveries where id=%s',(row['id'],)).fetchone()['state']=='read'


def test_closed_whatsapp_window_holds_report_until_patient_replies(world,monkeypatch):
    w=world;channel,calls=connect(w);store_pdf(w,w['encounter'])
    w['conn'].execute("update app.patient_channels set last_inbound_at=now()-interval '25 hours' where patient_id=%s",(w['patient'],))
    assert not w['service'].journey.tick()
    assert w['conn'].execute("select state from app.patient_deliveries where kind='report_pdf' and followup_id="
                             '(select id from app.followups where encounter_id=%s)',(w['encounter'],)).fetchone()['state']=='waiting_for_window'
    assert not any(c.get('type')=='document' for c in calls)


def test_explicit_voice_request_synthesizes_complete_prescription_in_native_language_only(world,monkeypatch):
    w=world;channel,calls=connect(w)
    class Speech:
        requests=[]
        def synthesize(self,text,language,voice,**kwargs):
            self.requests.append((text,language));return b'OggS-synthetic-test-audio'
    speech=Speech();w['service'].speech=speech
    monkeypatch.setattr(channel.graph,'upload_audio',lambda data,mime:'media-voice')
    assert not speech.requests
    post_event(w,channel.config,text_event('audio-request','VOICE'))
    assert w['service'].tick()
    for _ in range(3):w['service'].journey.tick()
    assert len(speech.requests)==1
    assert '1 गोली' in speech.requests[0][0] and '3 दिन' in speech.requests[0][0]
    assert speech.requests[0][1]=='auto'
    assert any(c.get('type')=='audio' for c in calls)
    jobs=w['conn'].execute("select state,language from app.patient_deliveries where kind='prescription_voice' and followup_id="
                           '(select id from app.followups where encounter_id=%s)',(w['encounter'],)).fetchall()
    assert jobs[-1]['state']=='accepted' and jobs[-1]['language']=='hi-IN'


def test_answered_questions_and_original_labs_are_visible_when_starting_next_visit(world):
    from voicerx.contracts.documents import ReportReading,ReportFinding
    w=world;choose_english(w)
    w['client'].post(w['base']+'/messages',json={'text':'How do I take Dolo?'})
    w['service'].reader=lambda data,mime:(ReportReading(is_medical_report=True,report_type='Synthetic lab',report_date=None,
        transcription='Synthetic value 10',medicines_named=[],findings=[ReportFinding(name='Synthetic value',value='10',unit='test units',
        reference_range='5–12',flag='normal',quote='Synthetic value 10')]),'pdf_text',1)
    original=b'%PDF-Original synthetic lab report'
    assert w['client'].post(w['base']+'/documents',content=original,headers={'Content-Type':'application/pdf'}).status_code==200
    eid=next_visit(w)
    history=w['client'].get(f"/api/v1/patients/{w['patient']}/journey").json()
    assert any(q['question']=='How do I take Dolo?' and q['cites']==['rx1'] for q in history['questions'])
    upload=history['uploads'][0]
    assert 'Synthetic value: 10 test units' in upload['summary']
    assert w['client'].get(upload['download_url']).content==original
    assert w['client'].post(f"/api/v1/patient-uploads/{upload['id']}/review").status_code==200
    assert w['client'].get(f"/api/v1/patients/{w['patient']}/journey").json()['uploads'][0]['reviewed_at']
    assert w['client'].get(f'/api/v1/encounters/{eid}').json()['patient']['id']==w['patient']


def test_unreadable_lab_original_still_saved_for_manual_review(world):
    w=world;choose_english(w);w['service'].reader=None
    original=b'%PDF-synthetic-needs-manual-review'
    response=w['client'].post(w['base']+'/documents',content=original,headers={'Content-Type':'application/pdf'})
    assert response.status_code==200
    history=w['client'].get(f"/api/v1/patients/{w['patient']}/journey").json()
    upload=history['uploads'][0]
    assert upload['summary_state']=='needs_review'
    assert w['client'].get(upload['download_url']).content==original
    assert any(t['kind']=='document' for t in history['tasks'])


def test_patient_history_and_original_files_keep_clinic_scope_and_csrf(world):
    from voicerx.app import auth
    w=world;choose_english(w)
    w['client'].post(w['base']+'/documents',content=b'%PDF-private-synthetic',headers={'Content-Type':'application/pdf'})
    upload=w['client'].get(f"/api/v1/patients/{w['patient']}/journey").json()['uploads'][0]
    csrf=w['client'].headers.pop('X-CSRF-Token')
    assert w['client'].post(f"/api/v1/patient-uploads/{upload['id']}/review").status_code==403
    w['client'].headers['X-CSRF-Token']=csrf
    token=auth.create_session(w['conn'],w['doc'],w['other'])
    w['client'].cookies.set(auth.COOKIE,token)
    w['client'].headers['X-CSRF-Token']=auth.load_session(w['conn'],token)['csrf_token']
    assert w['client'].get(f"/api/v1/patients/{w['patient']}/journey").status_code==404
    assert w['client'].get(upload['download_url']).status_code==404
    assert w['client'].post(f"/api/v1/patient-uploads/{upload['id']}/review").status_code==404


def test_signed_whatsapp_lab_upload_saves_original_and_creates_doctor_task(world,monkeypatch):
    w=world;channel,calls=connect(w)
    original=b'%PDF-synthetic-patient-inbound'
    monkeypatch.setattr(channel.graph,'download_media',lambda media_id:original)
    event={'id':'lab-upload-'+uuid4().hex,'from':'910000000001','type':'document',
           'document':{'id':'test-media','mime_type':'application/pdf'}}
    assert post_event(w,channel.config,event).status_code==200
    assert w['service'].tick()
    data=w['client'].get(f"/api/v1/patients/{w['patient']}/journey").json()
    assert w['client'].get(data['uploads'][0]['download_url']).content==original
    assert any(t['kind']=='document' for t in data['tasks'])
    from voicerx.agent.templates import load_templates
    acknowledgement=load_templates('hi-IN')['replies']['document_saved_review']
    assert any(call.get('text',{}).get('body')==acknowledgement for call in calls)


def test_contact_target_requires_consent_and_never_verifies_without_join(world):
    w=world;channel,calls=channel_for(w)
    path=f"/api/v1/patients/{w['patient']}/whatsapp-target"
    body={'phone':'+91 0000000001','language':'ta-IN','consent_confirmed':False}
    assert w['client'].post(path,json=body).status_code==422
    body['consent_confirmed']=True
    response=w['client'].post(path,json=body)
    assert response.status_code==200,response.text
    assert response.json()['needs_patient_join'] and not response.json()['linked']
    row=w['conn'].execute('select expected_contact from app.patient_contact_requests where patient_id=%s',(w['patient'],)).fetchone()
    assert row['expected_contact']==channel.contact('910000000001')
    assert not w['conn'].execute('select * from app.patient_channels where patient_id=%s',(w['patient'],)).fetchone()


def test_approved_pdf_download_recovers_from_private_archive_after_local_file_loss(world):
    w=world;expected=store_pdf(w,w['encounter'])
    artifact=w['conn'].execute("update app.artifacts set state='ready',file_name='missing-local-report.pdf',sha256=%s "
                               "where encounter_id=%s and kind='report_pdf' returning id",
                               (sha256(expected).hexdigest(),w['encounter'])).fetchone()
    response=w['client'].get(f"/api/v1/artifacts/{artifact['id']}/download")
    assert response.status_code==200 and response.content==expected
    assert response.headers['content-type']=='application/pdf'


def test_revoked_consent_cancels_queued_pdf_without_contacting_provider(world):
    w=world;channel,calls=connect(w);store_pdf(w,w['encounter'])
    before=len(calls)
    assert w['client'].post(w['base']+'/consent',json={'enabled':False}).status_code==200
    assert w['service'].journey.tick()
    job=w['conn'].execute("select state from app.patient_deliveries where followup_id=(select id from app.followups where encounter_id=%s)",(w['encounter'],)).fetchone()
    assert job['state']=='cancelled' and len(calls)==before


def test_spoken_voice_request_uses_same_explicit_outbox_and_keeps_transcript_source(world,monkeypatch):
    from types import SimpleNamespace
    from voicerx.agent.voice import transcribe_ogg_voice_note
    w=world
    from voicerx.app.followup import restore
    row=w['conn'].execute('select * from app.followups where encounter_id=%s',(w['encounter'],)).fetchone()
    conv=restore(w['conn'],row)
    speech=SimpleNamespace(transcribe=lambda *args,**kwargs:SimpleNamespace(text='VOICE'))
    w['service'].speech=speech
    # The decoder/length validator is covered by the WhatsApp adapter tests; exercise dispatch here.
    monkeypatch.setattr('voicerx.agent.voice.ogg_opus_seconds',lambda data:2.0)
    record=transcribe_ogg_voice_note(conv,b'synthetic-voice-input',speech,
        command=lambda text:w['service'].journey.command(w['conn'],conv,text=text,source='prisma'))
    assert record.transcript_source=='prisma' and record.raw_text=='VOICE'
    assert next(m for m in conv.messages if m.sender=='patient').voice
    assert w['conn'].execute("select count(*) as n from app.patient_deliveries where kind='prescription_voice' and followup_id=%s",
                             (conv.id,)).fetchone()['n']==1
