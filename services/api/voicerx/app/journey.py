"""Patient-level channels, approval deliveries and the next-visit digital history."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from ..agent import conversation as chat
from ..agent.documents import ALLOWED, MAGIC, MAX_BYTES, _note, items_from_document, receive_document
from ..agent.gate import GateRefused, check_report
from ..agent.prescription_audio import LANGUAGES, prescription_text, requested_language, requested_voice
from ..agent.redflags import find_red_flags
from ..contracts.followup import Button, Conversation, Message
from ..ingest.gnani import CLINIC_VOICE, TTS_MODEL
from .db import all_rows, audit, one, transaction


def moment():
    return datetime.now(timezone.utc)


def queue(conn, conv, kind, request_ref, language=None):
    return one(conn, 'insert into app.patient_deliveries(id,followup_id,kind,request_ref,language) '
               'values(%s,%s,%s,%s,%s) on conflict(followup_id,kind,request_ref) do nothing returning *',
               ('delivery-'+uuid4().hex[:20], conv.id, kind, request_ref, language))


def inherit_channel(conn, conv):
    link = one(conn, 'select * from app.patient_channels where patient_id=%s and organisation_id=%s',
               (conv.patient_id, conv.clinic_id))
    if link and not link['opted_out_at']:
        conv.contact, conv.last_inbound_at = link['contact'], link['last_inbound_at']
        conv.plan.channel = 'whatsapp'
        conn.execute("update app.followups set conversation=jsonb_set(conversation,'{superseded}','true') "
                     'where organisation_id=%s and patient_id=%s and id<>%s', (conv.clinic_id,conv.patient_id,conv.id))


def link_channel(conn, conv):
    expected=one(conn,'select expected_contact from app.patient_contact_requests where patient_id=%s and organisation_id=%s',
                 (conv.patient_id,conv.clinic_id))
    if expected and expected['expected_contact'] != conv.contact:
        raise GateRefused('The invitation was issued for a different WhatsApp number.')
    existing = one(conn, 'select * from app.patient_channels where contact=%s for update', (conv.contact,))
    if existing and (existing['patient_id'] != conv.patient_id or existing['organisation_id'] != conv.clinic_id):
        raise GateRefused('This WhatsApp contact is already linked to another patient. The clinic must reconcile it.')
    if existing and existing['opted_out_at']:
        raise GateRefused('Follow-up was stopped. Renew consent with the clinic before linking again.')
    conn.execute('insert into app.patient_channels(patient_id,organisation_id,contact,last_inbound_at) '
                 'values(%s,%s,%s,%s) on conflict(patient_id) do update set contact=excluded.contact, '
                 'last_inbound_at=excluded.last_inbound_at,verified_at=now()',
                 (conv.patient_id,conv.clinic_id,conv.contact,conv.last_inbound_at))


def menu(conv):
    for message in conv.messages[-2:]:
        if message.sender == 'clinic' and any(b.id == 'menu_medicines' for b in message.buttons):
            ids = {b.id for b in message.buttons}
            for key,label in [('menu_pdf','Approved report PDF'),('menu_voice','Prescription voice'),('menu_findings','Visit findings')]:
                if key not in ids:
                    message.buttons.append(Button(id=key,label=label))


def deliveries(conn, followup_id):
    return [{**r,'updated_at':r['updated_at'].isoformat()} for r in all_rows(conn,
            'select id,kind,language,state,error,updated_at from app.patient_deliveries where followup_id=%s '
            'order by created_at', (followup_id,))]


class Journey:
    def __init__(self, service):
        self.service = service

    def command(self, conn, conv, text=None, button=None, source='typed'):
        """Explicit delivery requests only; warning signs and STOP always stay with the core router."""
        value = (text or '').strip().lower()
        if find_red_flags(text or '') or value in ('stop','unsubscribe'):
            return False
        voice = requested_voice(text, button)
        pdf = button == 'menu_pdf' or value in ('pdf','report','send report','my report','report pdf')
        findings = button == 'menu_findings' or value in ('findings','show findings','my findings','what did the doctor find')
        if not (voice or pdf or findings):
            return False
        if conv.stopped or conv.superseded:
            raise GateRefused('This conversation is stopped or a newer visit is active.')
        check_report(conv,conv._visit.approved)
        conv.clock += chat.STEP
        conv.messages.append(Message(id=f'm{len(conv.messages)+1}',sender='patient',text=text or button,at=conv.clock,
                                     voice=source=='prisma'))
        record = chat._record(conv,text or button, 'button' if button else source, 'answered' if findings else 'recorded', [])
        if findings:
            lines = ['What your doctor recorded in the approved visit:']
            cites=[]
            for section in ('examination','investigation_results','diagnoses','follow_up'):
                for line in conv._visit.approved.sections.get(section,[]):
                    lines.append(section.replace('_',' ')+': '+line.text);cites.extend(line.cites)
            lines.append('Questions about what these findings mean go to your doctor. Reply DOCTOR to contact the clinic.')
            chat._reply(conv,record,'text','\n'.join(lines),cites=list(dict.fromkeys(cites)))
        elif voice:
            language = requested_language(text,conv._visit.approved.language_pref)
            if language not in LANGUAGES:
                reply = 'Prescription audio is available in Hindi, English, Tamil, Telugu and Gujarati. Please name one of these languages.'
            elif self.service.speech is None:
                reply = 'Prescription audio is unavailable on this server. Your written prescription is still available.'
            else:
                queue(conn,conv,'prescription_voice',record.id,language)
                reply = f'I am preparing your complete approved prescription voice note in {LANGUAGES[language]}.'
            chat._reply(conv,record,'text',reply)
        else:
            queue(conn,conv,'report_pdf',record.id)
            chat._reply(conv,record,'text','Your approved report PDF is queued. It will be sent here when the file is ready.')
        return True

    def upload(self, conn, conv, data, mime):
        mime=(mime or '').split(';')[0].lower().strip()
        valid = mime in ALLOWED and len(data)<=MAX_BYTES and MAGIC[mime](data)
        digest=sha256(data).hexdigest()
        existing=one(conn,'select id from app.patient_uploads where organisation_id=%s and patient_id=%s and sha256=%s',
                     (conv.clinic_id,conv.patient_id,digest)) if valid else None
        if existing:
            record=chat._record(conv,'Repeated report upload','document','recorded',[])
            chat._reply(conv,record,'text','This report is already saved in your clinic history for the doctor.')
            return
        record,doc=receive_document(conv,data,mime,self.service.reader,original_saved=valid)
        templates=chat.load_templates(conv.language)['replies']
        refused = record.reply_text in (templates['document_refused'],templates['document_not_report'])
        if valid and not refused:
            summary=_note(doc.reading) if doc else 'Original report saved. Automatic summary unavailable; doctor review required.'
            upload_id='upload-'+uuid4().hex[:20]
            conn.execute('insert into app.patient_uploads(id,organisation_id,patient_id,encounter_id,mime,sha256,data,summary,reading,summary_state) '
                         'values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (upload_id,conv.clinic_id,conv.patient_id,conv.visit_id,mime,digest,data,summary,
                          Jsonb(doc.reading.model_dump(mode='json')) if doc else None,'ready' if doc else 'needs_review'))
            if not doc:
                chat._task(conv,'document',record,summary)
        if doc and self.service.memory.add_document(doc):
            self.service.memory.add(items_from_document(doc))

    def tick(self):
        """A database-locked outbox; acceptance is separate from provider delivery/read receipts."""
        from .followup import restore
        if not self.service.channel:
            return False
        with self.service.lock,transaction() as conn:
            job=one(conn,"select * from app.patient_deliveries where state in ('pending','waiting_for_contact',"
                    "'waiting_for_window','waiting_for_artifact') and not_before<=now() order by created_at "
                    'limit 1 for update skip locked')
            if not job:
                return False
            row=one(conn,'select * from app.followups where id=%s for update',(job['followup_id'],))
            try:
                conv=restore(conn,row)
                if conv.stopped or conv.superseded:
                    raise GateRefused('Stopped or newer visit active.')
                if not conv.contact or conv.plan.channel!='whatsapp':
                    return self.hold(conn,job,'waiting_for_contact')
                link=one(conn,'select * from app.patient_channels where patient_id=%s and organisation_id=%s',
                         (conv.patient_id,conv.clinic_id))
                if link and link['opted_out_at']:
                    raise GateRefused('The patient opted out.')
                number=next((n for n in self.service.channel.config.test_numbers
                             if self.service.channel.contact(n)==conv.contact),None)
                if not number:
                    return self.hold(conn,job,'waiting_for_contact')
                inbound=link['last_inbound_at'] if link else conv.last_inbound_at
                if not inbound or moment()-inbound>timedelta(hours=24):
                    return self.hold(conn,job,'waiting_for_window')
                graph=self.service.channel.graph
                if job['kind']=='report_pdf':
                    file=one(conn,'select * from app.report_files where encounter_id=%s and version=%s',
                             (row['encounter_id'],row['version']))
                    if not file:
                        # Existing approved PDFs can be archived lazily from their verified artifact.
                        artifact=one(conn,"select * from app.artifacts where encounter_id=%s and version=%s and kind='report_pdf' and state='ready'",
                                     (row['encounter_id'],row['version']))
                        path=(self.service.settings.artifacts_dir/row['encounter_id']/f"v{row['version']}"/artifact['file_name']) if artifact else None
                        if not path or not path.is_file():
                            return self.hold(conn,job,'waiting_for_artifact')
                        data=path.read_bytes()
                        if sha256(data).hexdigest()!=artifact['sha256']:
                            raise GateRefused('PDF fingerprint does not match its artifact.')
                        conn.execute('insert into app.report_files(encounter_id,version,sha256,data) values(%s,%s,%s,%s) on conflict do nothing',
                                     (row['encounter_id'],row['version'],artifact['sha256'],data))
                    else:
                        data=bytes(file['data'])
                        if sha256(data).hexdigest()!=file['sha256']:
                            raise GateRefused('Archived PDF fingerprint changed.')
                    filename=f"approved-report-v{row['version']}.pdf"
                    media=graph.upload_document(data,filename)
                    result=graph.send_document(number,media,filename,'Your doctor-approved visit report. Reply VOICE for your prescription in your native language.')
                else:
                    text=prescription_text(conv._visit.approved,job['language'])
                    cache=self.service.settings.artifacts_dir/'prescription-audio'
                    cache.mkdir(parents=True,exist_ok=True)
                    digest=sha256((TTS_MODEL+CLINIC_VOICE+job['language']+text).encode()).hexdigest()
                    path=cache/(digest+'.ogg')
                    if not path.exists():
                        data=self.service.speech.synthesize(text,'auto' if job['language']!='en-IN' else 'en-IN',
                                                           CLINIC_VOICE,container='ogg',sample_rate=24000)
                        if not data.startswith(b'OggS'):
                            raise ValueError('Speech provider did not return Ogg audio.')
                        path.write_bytes(data)
                    result=graph.send_audio(number,graph.upload_audio(path.read_bytes(),'audio/ogg'),voice=True)
                provider=result['messages'][0]['id']
                conn.execute("update app.patient_deliveries set state='accepted',provider_id=%s,error=null,attempts=attempts+1,updated_at=now() where id=%s",
                             (provider,job['id']))
                conn.execute('insert into app.whatsapp_receipts(message_id,followup_id,message_ref) values(%s,%s,%s) on conflict do nothing',
                             (provider,conv.id,job['id']))
                audit(conn,None,conv.clinic_id,'patient_delivery.accepted','followup',conv.id,{'kind':job['kind'],'version':row['version']})
            except GateRefused as error:
                conn.execute("update app.patient_deliveries set state='cancelled',error=%s,updated_at=now() where id=%s",(str(error),job['id']))
            except Exception as error:
                count=job['attempts']+1
                conn.execute("update app.patient_deliveries set state=%s,attempts=%s,error=%s,not_before=now()+interval '1 minute',updated_at=now() where id=%s",
                             ('failed' if count>=3 else 'pending',count,type(error).__name__,job['id']))
            return True

    def hold(self,conn,job,state):
        conn.execute("update app.patient_deliveries set state=%s,not_before=now()+interval '15 seconds',updated_at=now() where id=%s",(state,job['id']))
        return False


def history(conn, organisation_id, patient_id):
    rows=all_rows(conn,'select f.*,e.visit_date from app.followups f join app.encounters e on e.id=f.encounter_id '
                  'where f.organisation_id=%s and f.patient_id=%s order by e.visit_date desc,f.updated_at desc',
                  (organisation_id,patient_id))
    questions=[];tasks=[]
    for row in rows:
        conv=Conversation.model_validate(row['conversation'])
        task_records={t.record_id for t in conv.tasks}
        for record in conv.records:
            if record.action in ('answered','escalated','urgent') or record.id in task_records:
                questions.append({'id':record.id,'encounter_id':row['encounter_id'],'visit_date':str(row['visit_date']),
                                  'at':record.received_at.isoformat(),'question':record.raw_text,'reply':record.reply_text,
                                  'cites':record.reply_cites,'action':record.action,'source':record.transcript_source,
                                  'report_hash':record.report_hash})
        tasks.extend({**t.model_dump(mode='json'),'encounter_id':row['encounter_id']} for t in conv.tasks)
    uploads=all_rows(conn,'select id,encounter_id,mime,summary,reading,summary_state,received_at,reviewed_by,reviewed_at '
                     'from app.patient_uploads where organisation_id=%s and patient_id=%s order by received_at desc',
                     (organisation_id,patient_id))
    for upload in uploads:
        upload['received_at']=upload['received_at'].isoformat()
        upload['reviewed_at']=upload['reviewed_at'].isoformat() if upload['reviewed_at'] else None
        upload['download_url']='/api/v1/patient-uploads/'+upload['id']+'/download'
    link=one(conn,'select verified_at,last_inbound_at,opted_out_at from app.patient_channels where organisation_id=%s and patient_id=%s',
             (organisation_id,patient_id))
    if not link:
        selected=one(conn,'select a.updated_at as verified_at,w.last_inbound_at,w.opted_out_at from app.whatsapp_active_reports a '
                     'join app.followups f on f.id=a.followup_id join app.whatsapp_contact_windows w on w.contact=a.contact '
                     'where f.organisation_id=%s and f.patient_id=%s',(organisation_id,patient_id))
        link=selected
    return {'patient_id':patient_id,'questions':sorted(questions,key=lambda q:q['at'],reverse=True),'tasks':tasks,'uploads':uploads,
            'whatsapp':{'linked':bool(link),'opted_out':bool(link and link['opted_out_at']),
                        'last_inbound_at':link['last_inbound_at'].isoformat() if link and link['last_inbound_at'] else None}}
