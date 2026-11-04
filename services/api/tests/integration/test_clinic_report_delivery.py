"""Clinic test copies use signed report-specific buttons, independent of patient phone links."""
from dataclasses import replace
from datetime import datetime, timezone

from test_dashboard_followup import world, channel_for, post_event, text_event, pytestmark
from test_patient_journey import next_visit, store_pdf, connect
from voicerx.app.clinic_reports import ClinicTarget, VOICE_PREFIX


class Speech:
    def __init__(self):self.requests=[]
    def synthesize(self,text,language,voice,**kwargs):
        self.requests.append((text,language));return b'OggS-synthetic-clinic-audio'


def setup(w,monkeypatch,channel=None):
    if channel is None:channel,calls=channel_for(w)
    else:channel,calls=channel
    w['service'].speech=Speech()
    w['service'].clinic_reports.target=ClinicTarget(w['org'],'910000000001')
    w['conn'].execute('insert into app.clinic_report_contacts(organisation_id,contact,last_inbound_at) values(%s,%s,now())',
                      (w['org'],channel.contact('910000000001')))
    monkeypatch.setattr(channel.graph,'upload_document',lambda data,name:'pdf-media')
    monkeypatch.setattr(channel.graph,'upload_audio',lambda data,mime:'voice-media')
    return channel,calls


def approve_without_patient_link(w):
    w['conn'].execute("update app.patients set consents=array_remove(consents,'followup_whatsapp') where id=%s",(w['patient'],))
    eid=next_visit(w);store_pdf(w,eid)
    return eid


def jobs(w,eid):
    return w['conn'].execute('select * from app.clinic_report_jobs where encounter_id=%s order by kind',(eid,)).fetchall()


def button(mid,pdf_id,sender='910000000001'):
    return {'id':mid,'from':sender,'type':'interactive',
            'interactive':{'type':'button_reply','button_reply':{'id':VOICE_PREFIX+pdf_id,'title':'Prescription voice'}}}


def test_approval_without_patient_whatsapp_consent_sends_a_clinic_pdf_and_voice_option_only(world,monkeypatch):
    w=world;channel,calls=setup(w,monkeypatch);eid=approve_without_patient_link(w)
    assert {j['kind'] for j in jobs(w,eid)}=={'report_pdf','voice_option'}
    assert not w['conn'].execute('select id from app.followups where encounter_id=%s',(eid,)).fetchone()
    assert not w['conn'].execute('select patient_id from app.patient_channels where patient_id=%s',(w['patient'],)).fetchone()
    for _ in range(2):assert w['service'].clinic_reports.tick()
    assert [c['type'] for c in calls]==['document','interactive']
    assert not w['service'].speech.requests
    pdf=next(j for j in jobs(w,eid) if j['kind']=='report_pdf')
    assert calls[-1]['interactive']['action']['buttons'][0]['reply']['id']==VOICE_PREFIX+pdf['id']
    post_event(w,channel.config,statuses=[{'id':pdf['provider_id'],'status':'read'}])
    post_event(w,channel.config,statuses=[{'id':pdf['provider_id'],'status':'sent'}])
    assert next(j for j in jobs(w,eid) if j['kind']=='report_pdf')['state']=='read'
    assert w['client'].get(f'/api/v1/encounters/{eid}/report').json()['clinic_deliveries']


def test_signed_voice_button_is_recipient_bound_and_uses_its_original_report_version(world,monkeypatch):
    w=world;channel,calls=setup(w,monkeypatch);eid=approve_without_patient_link(w)
    for _ in range(2):w['service'].clinic_reports.tick()
    pdf=next(j for j in jobs(w,eid) if j['kind']=='report_pdf')
    channel.config=replace(channel.config,test_numbers=frozenset({'910000000001','910000000002'}))
    post_event(w,channel.config,button('wrong-phone',pdf['id'],'910000000002'));assert w['service'].tick()
    assert not any(j['kind']=='prescription_voice' for j in jobs(w,eid))
    # A later visit must not cause a button on the earlier PDF to read the later prescription.
    next_visit(w)
    post_event(w,channel.config,button('requested-voice',pdf['id']));assert w['service'].tick()
    post_event(w,channel.config,button('requested-voice',pdf['id']))
    assert len([j for j in jobs(w,eid) if j['kind']=='prescription_voice'])==1
    for _ in range(5):
        if next(j for j in jobs(w,eid) if j['kind']=='prescription_voice')['state']=='accepted':break
        w['service'].clinic_reports.tick()
    voice=next(j for j in jobs(w,eid) if j['kind']=='prescription_voice')
    assert voice['version']==pdf['version'] and voice['source_hash']==pdf['source_hash']
    assert len(w['service'].speech.requests)==1 and calls[-1]['type']=='audio'


def test_closed_window_waits_and_new_signed_message_resumes_without_a_patient_join(world,monkeypatch):
    w=world;channel,calls=setup(w,monkeypatch);eid=approve_without_patient_link(w)
    w['conn'].execute("update app.clinic_report_contacts set last_inbound_at=now()-interval '25 hours' where organisation_id=%s",(w['org'],))
    assert not w['service'].clinic_reports.tick() and not calls
    post_event(w,channel.config,text_event('hello-clinic','hello'));assert w['service'].tick()
    assert w['service'].clinic_reports.tick() and calls[0]['type']=='document'
    w['conn'].execute("update app.clinic_report_contacts set last_inbound_at=now()-interval '25 hours' where organisation_id=%s",(w['org'],))
    post_event(w,channel.config,text_event('hello-clinic','hello'))
    last=w['conn'].execute('select last_inbound_at from app.clinic_report_contacts where organisation_id=%s',(w['org'],)).fetchone()['last_inbound_at']
    assert (datetime.now(timezone.utc)-last).total_seconds()>24*3600


def test_stop_prevents_clinic_copies_and_patient_links_are_not_reassigned(world,monkeypatch):
    w=world;channel,calls=setup(w,monkeypatch);eid=approve_without_patient_link(w)
    post_event(w,channel.config,text_event('stop-clinic','STOP'))
    assert w['service'].clinic_reports.tick()
    assert next(j for j in jobs(w,eid) if j['kind']=='report_pdf')['state']=='cancelled'
    assert not calls


def test_same_number_does_not_receive_both_patient_and_clinic_pdf_for_one_approval(world,monkeypatch):
    w=world;channel,calls=connect(w);setup(w,monkeypatch,(channel,calls))
    eid=next_visit(w)
    assert {j['kind'] for j in jobs(w,eid)}=={'report_pdf','voice_option'}
    assert not w['conn'].execute('select d.id from app.patient_deliveries d join app.followups f on f.id=d.followup_id where f.encounter_id=%s',
                                 (eid,)).fetchall()


def test_failed_delivery_is_visible_and_retry_requires_csrf_and_clinic_scope(world,monkeypatch):
    from voicerx.agent.whatsapp import WhatsAppError
    from voicerx.app import auth
    w=world;channel,calls=setup(w,monkeypatch);eid=approve_without_patient_link(w)
    def blocked(*args,**kwargs):raise WhatsAppError(400,'API access blocked')
    monkeypatch.setattr(channel.graph,'send_document',blocked)
    for _ in range(3):
        w['conn'].execute("update app.clinic_report_jobs set not_before=now() where encounter_id=%s and kind='report_pdf'",(eid,))
        assert w['service'].clinic_reports.tick()
    pdf=next(j for j in jobs(w,eid) if j['kind']=='report_pdf')
    assert pdf['state']=='failed' and pdf['error']=='WhatsApp HTTP 400'
    path=f'/api/v1/encounters/{eid}/clinic-reports'
    assert any(j['state']=='failed' for j in w['client'].get(path).json()['items'])
    csrf=w['client'].headers.pop('X-CSRF-Token')
    assert w['client'].post(path+'/retry').status_code==403
    w['client'].headers['X-CSRF-Token']=csrf
    assert w['client'].post(path+'/retry').status_code==200
    assert next(j for j in jobs(w,eid) if j['kind']=='report_pdf')['state']=='pending'
    token=auth.create_session(w['conn'],w['doc'],w['other'])
    w['client'].cookies.set(auth.COOKIE,token)
    w['client'].headers['X-CSRF-Token']=auth.load_session(w['conn'],token)['csrf_token']
    assert w['client'].get(path).status_code==404
    assert w['client'].post(path+'/retry').status_code==404
