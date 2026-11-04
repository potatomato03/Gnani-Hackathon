"""Approval-triggered copies to an explicitly configured clinic test number, never a patient rebind."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from ..agent.gate import GateRefused
from ..agent.prescription_audio import LANGUAGES, prescription_text
from ..agent.whatsapp import WhatsAppError, digits
from ..contracts.report import ApprovedReport
from ..ingest.gnani import TTS_MODEL, CLINIC_VOICE
from ..pipeline.assemble import content_hash
from .config import read_env
from .db import all_rows, audit, one, transaction

VOICE_PREFIX = 'report_voice:'
RANK = {'accepted':0,'sent':1,'delivered':2,'read':3,'failed':4}


@dataclass(frozen=True)
class ClinicTarget:
    organisation_id: str
    number: str


class ClinicReports:
    def __init__(self, service):
        self.service = service
        env = read_env()
        number = digits(env.get('WHATSAPP_CLINIC_REPORT_NUMBER'))
        org = env.get('WHATSAPP_CLINIC_REPORT_ORG')
        self.target = ClinicTarget(org,number) if org and number and service.channel and service.channel.allowed(number) else None

    def insert(self, conn, **values):
        return one(conn,'insert into app.clinic_report_jobs(id,organisation_id,approval_id,encounter_id,version,source_hash,'
                   'recipient,kind,source_job,request_ref,language) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
                   'on conflict(approval_id,recipient,kind,request_ref) do nothing returning *',
                   ('notice-'+uuid4().hex[:20],*[values[k] for k in ('organisation_id','approval_id','encounter_id','version',
                     'source_hash','recipient','kind','source_job','request_ref','language')]))

    def queue_approval(self, conn, encounter, approved, patient, approval_id):
        target = self.target
        if not target or target.organisation_id != encounter['organisation_id']:
            return None
        if not patient['synthetic'] or not approved.record_snapshot['patient'].get('synthetic'):
            return None
        if approved.status!='approved' or content_hash(approved)!=approved.content_hash:
            raise GateRefused('Only an intact approved report can be copied.')
        contact = self.service.channel.contact(target.number)
        # Reuse only the verified phone's message-window timestamp, not its patient identity or consent.
        link=one(conn,'select last_inbound_at from app.patient_channels where organisation_id=%s and contact=%s',
                 (target.organisation_id,contact))
        conn.execute('insert into app.clinic_report_contacts(organisation_id,contact,last_inbound_at) values(%s,%s,%s) '
                     'on conflict do nothing',(target.organisation_id,contact,link['last_inbound_at'] if link else None))
        base=dict(organisation_id=target.organisation_id,approval_id=approval_id,encounter_id=encounter['id'],
                  version=approved.version,source_hash=approved.content_hash,recipient=contact,
                  request_ref='approval',language=approved.language_pref)
        pdf=self.insert(conn,**base,kind='report_pdf',source_job=None)
        if pdf and approved.language_pref in LANGUAGES and self.service.speech is not None:
            self.insert(conn,**base,kind='voice_option',source_job=pdf['id'])
        return pdf

    def touch(self, conn, item):
        """Called only after a new signed inbound event is inserted; replay cannot extend the window."""
        target=self.target
        if not target or item['sender']!=self.service.channel.contact(target.number):
            return
        contact=item['sender'];now=datetime.now(timezone.utc)
        conn.execute('insert into app.clinic_report_contacts(organisation_id,contact,last_inbound_at) values(%s,%s,%s) '
                     'on conflict(organisation_id,contact) do update set last_inbound_at=excluded.last_inbound_at',
                     (target.organisation_id,contact,now))
        text=(item.get('text') or '').strip().lower()
        if text in ('stop','unsubscribe','start reports'):
            conn.execute('update app.clinic_report_contacts set opted_out_at=%s where organisation_id=%s and contact=%s',
                         (None if text=='start reports' else now,target.organisation_id,contact))
        conn.execute("update app.clinic_report_jobs set not_before=now() where organisation_id=%s and recipient=%s "
                     "and state='waiting_for_window'",(target.organisation_id,contact))

    def receive(self, conn, item):
        button=item.get('button') or ''
        requested=button.startswith(VOICE_PREFIX)
        target=self.target
        if not target or item['sender']!=self.service.channel.contact(target.number):
            return requested  # A report button from another phone never enters a patient conversation.
        contact=item['sender']
        if not requested:
            return (item.get('text') or '').strip().lower()=='start reports'
        source=one(conn,"select * from app.clinic_report_jobs where id=%s and organisation_id=%s and recipient=%s "
                   "and kind='report_pdf' and state in ('accepted','sent','delivered','read')",
                   (button[len(VOICE_PREFIX):],target.organisation_id,contact))
        if source:
            self.insert(conn,**{k:source[k] for k in ('organisation_id','approval_id','encounter_id','version','source_hash',
                        'recipient','language')},kind='prescription_voice',source_job=source['id'],request_ref=item['message_id'])
            audit(conn,None,target.organisation_id,'clinic_report.voice_requested','encounter',source['encounter_id'],
                  {'version':source['version']})
        return True

    def receipt(self, conn, receipt):
        status=receipt.get('status')
        if status not in RANK:
            return
        row=one(conn,'select id,state from app.clinic_report_jobs where provider_id=%s for update',(receipt.get('id'),))
        if row and RANK[status]>=RANK.get(row['state'],0):
            conn.execute('update app.clinic_report_jobs set state=%s,updated_at=now() where id=%s',(status,row['id']))

    def tick(self):
        target=self.target
        if not target:
            return False
        with self.service.lock, transaction() as conn:
            job=one(conn,"select * from app.clinic_report_jobs where organisation_id=%s and state in "
                    "('pending','waiting_for_window','waiting_for_artifact') and not_before<=now() "
                    "order by created_at,case kind when 'report_pdf' then 0 when 'voice_option' then 1 else 2 end,id "
                    'limit 1 for update skip locked',(target.organisation_id,))
            if not job:
                return False
            def hold(state):
                conn.execute("update app.clinic_report_jobs set state=%s,not_before=now()+interval '15 seconds',updated_at=now() "
                             'where id=%s',(state,job['id']))
                return False
            try:
                if self.service.channel.contact(target.number)!=job['recipient']:
                    raise GateRefused('Clinic test recipient changed.')
                contact=one(conn,'select * from app.clinic_report_contacts where organisation_id=%s and contact=%s',
                            (target.organisation_id,job['recipient']))
                if contact and contact['opted_out_at']:
                    raise GateRefused('Clinic recipient stopped reports.')
                if not contact or not contact['last_inbound_at'] or datetime.now(timezone.utc)-contact['last_inbound_at']>timedelta(hours=24):
                    return hold('waiting_for_window')
                row=one(conn,"select r.report,p.synthetic from app.report_versions r join app.encounters e on e.id=r.encounter_id "
                        "join app.patients p on p.id=e.patient_id where r.encounter_id=%s and r.version=%s and r.status='approved' "
                        'and e.organisation_id=%s',(job['encounter_id'],job['version'],target.organisation_id))
                if not row or not row['synthetic']:
                    raise GateRefused('Clinic copies are limited to approved synthetic visits.')
                report=ApprovedReport.model_validate(row['report'])
                if report.content_hash!=job['source_hash'] or content_hash(report)!=job['source_hash'] or not report.record_snapshot['patient'].get('synthetic'):
                    raise GateRefused('Approved report fingerprint changed.')
                graph=self.service.channel.graph
                if job['kind']=='report_pdf':
                    file=one(conn,'select sha256,data from app.report_files where encounter_id=%s and version=%s',
                             (job['encounter_id'],job['version']))
                    if not file:
                        return hold('waiting_for_artifact')
                    data=bytes(file['data'])
                    if sha256(data).hexdigest()!=file['sha256']:
                        raise GateRefused('Archived PDF fingerprint changed.')
                    filename=f"approved-report-{job['encounter_id']}-v{job['version']}.pdf"
                    voice=one(conn,"select id from app.clinic_report_jobs where source_job=%s and kind='voice_option'",(job['id'],))
                    caption=f'Clinic copy: {report.header.patient_name}. Approved visit {report.header.visit_date}.'
                    if voice:
                        caption+=' Prescription voice option follows.'
                    result=graph.send_document(target.number,graph.upload_document(data,filename),filename,caption)
                elif job['kind']=='voice_option':
                    source=one(conn,'select state from app.clinic_report_jobs where id=%s',(job['source_job'],))
                    if not source or source['state'] not in ('accepted','sent','delivered','read'):
                        return hold('waiting_for_artifact')
                    result=graph.send_buttons(target.number,
                        f'{report.header.patient_name} — visit {report.header.visit_date}, version {report.version}. '
                        f'Listen to the approved prescription in {LANGUAGES[job["language"]]}:',
                        [(VOICE_PREFIX+job['source_job'],'Prescription voice')])
                else:
                    if self.service.speech is None:
                        raise GateRefused('Prescription speech is not configured.')
                    text=prescription_text(report,job['language'])
                    cache=self.service.settings.artifacts_dir/'prescription-audio';cache.mkdir(parents=True,exist_ok=True)
                    path=cache/(sha256((TTS_MODEL+CLINIC_VOICE+job['language']+text).encode()).hexdigest()+'.ogg')
                    if not path.exists():
                        audio=self.service.speech.synthesize(text,'auto' if job['language']!='en-IN' else 'en-IN',
                                                             CLINIC_VOICE,container='ogg',sample_rate=24000)
                        if not audio.startswith(b'OggS'):
                            raise ValueError('Speech provider did not return Ogg audio.')
                        path.write_bytes(audio)
                    result=graph.send_audio(target.number,graph.upload_audio(path.read_bytes(),'audio/ogg'),voice=True)
                provider=result['messages'][0]['id']
                conn.execute("update app.clinic_report_jobs set state='accepted',provider_id=%s,error=null,attempts=attempts+1,"
                             'updated_at=now() where id=%s',(provider,job['id']))
                audit(conn,None,target.organisation_id,'clinic_report.accepted','encounter',job['encounter_id'],
                      {'kind':job['kind'],'version':job['version']})
            except GateRefused as error:
                conn.execute("update app.clinic_report_jobs set state='cancelled',error=%s,updated_at=now() where id=%s",(str(error),job['id']))
            except Exception as error:
                attempts=job['attempts']+1
                detail=f'WhatsApp HTTP {error.status}' if isinstance(error,WhatsAppError) else type(error).__name__
                conn.execute("update app.clinic_report_jobs set state=%s,attempts=%s,error=%s,not_before=now()+interval '1 minute',"
                             'updated_at=now() where id=%s',('failed' if attempts>=3 else 'pending',attempts,detail,job['id']))
            return True


def deliveries(conn, encounter_id, version):
    return [{**r,'updated_at':r['updated_at'].isoformat()} for r in all_rows(conn,
        'select id,kind,language,state,error,updated_at from app.clinic_report_jobs where encounter_id=%s and version=%s order by created_at,id',
        (encounter_id,version))]
