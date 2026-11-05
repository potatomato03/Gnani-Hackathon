"""Bridge the WhatsApp agent to authenticated, versioned dashboard records.

Patient replies remain separate from the clinical report. Webhooks enter a durable inbox; only a
single-use invitation can bind a test phone to a visit. No phone number is stored in the inbox.
"""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import logging
import secrets
import threading
from uuid import uuid4

from psycopg.types.json import Jsonb

from ..agent import conversation as chat
from ..agent.documents import items_from_document, receive_document
from ..agent.gate import CONSENT, GateRefused
from ..agent.memory import LocalMemoryStore, SafeMemory, SupabaseMemoryStore, items_from_record
from ..agent.templates import SUPPORTED
from ..agent.understand import make_nlu
from ..agent.visits import Visit
from ..agent.voice import transcribe_ogg_voice_note
from ..agent.whatsapp import JOIN, WhatsAppChannel, parse_webhook
from ..contracts.followup import Conversation, TASK_ORDER
from ..contracts.report import ApprovedReport
from ..ingest.gnani import speech_from_env
from ..llm.client import build_client
from ..pipeline.assemble import content_hash
from .config import REPO_ROOT
from .db import all_rows, audit, one, transaction
from .journey import Journey, deliveries, inherit_channel, link_channel, menu, queue
from .clinic_reports import ClinicReports

log = logging.getLogger('voicerx.followup')
AUTO = object()


def now():
    return datetime.now(timezone.utc)


def visit_for(encounter, approved, patient):
    if approved.header.patient_id != encounter['patient_id'] or patient['id'] != encounter['patient_id']:
        raise GateRefused('The approved report belongs to another patient.')
    if not patient['synthetic'] or not approved.record_snapshot['patient'].get('synthetic'):
        raise GateRefused('The WhatsApp bot is limited to synthetic visits.')
    if content_hash(approved) != approved.content_hash:
        raise GateRefused('The approved report fingerprint changed.')
    if CONSENT not in patient['consents']:
        raise GateRefused('Follow-up consent is required.')
    return Visit(visit_id=encounter['id'], case_id=approved.case_id, source='dashboard', path='',
                 clinic_id=encounter['organisation_id'], approved=approved, consents=list(patient['consents']))


def context(conn, encounter_id):
    encounter = one(conn, 'select e.* from app.encounters e join app.organisations o on o.id=e.organisation_id '
                    'where e.id = %s and o.archived_at is null', (encounter_id,))
    if not encounter or not encounter['approved_version']:
        raise GateRefused('Approve this visit before starting follow-up.')
    row = one(conn, "select report from app.report_versions where encounter_id = %s and version = %s "
              "and status = 'approved'", (encounter_id, encounter['approved_version']))
    patient = one(conn, 'select * from app.patients where id = %s', (encounter['patient_id'],))
    return visit_for(encounter, ApprovedReport.model_validate(row['report']), patient)


def initialize(conn, encounter, approved, patient, clinic_copy_contact=None,registered_delivery=False):
    """Called in the approval transaction. Failure of eligibility never reverses approval."""
    existing = one(conn, 'select * from app.followups where encounter_id = %s and version = %s',
                   (encounter['id'], approved.version))
    if existing:
        return existing
    visit = visit_for(encounter, approved, patient)
    conv = chat.start(visit, 'fu' + uuid4().hex[:20], ask_language=True)
    conv.visit_id = visit.visit_id
    conv.patient_key = 'app-' + sha256(f'{visit.clinic_id}/{conv.patient_id}'.encode()).hexdigest()[:32]
    inherit_channel(conn,conv)
    menu(conv)
    row = one(conn, 'insert into app.followups (id, encounter_id, version, organisation_id, patient_id, conversation) '
               'values (%s,%s,%s,%s,%s,%s) returning *',
               (conv.id, encounter['id'], approved.version, visit.clinic_id, conv.patient_id,
                Jsonb(conv.model_dump(mode='json'))))
    if not registered_delivery and (not clinic_copy_contact or conv.contact != clinic_copy_contact):
        queue(conn,conv,'report_pdf','approval')
    return row


def restore(conn, row):
    visit = context(conn, row['encounter_id'])
    conv = Conversation.model_validate(row['conversation'])
    if conv.report_hash != visit.approved.content_hash or row['version'] != visit.approved.version:
        raise GateRefused('This follow-up belongs to a superseded approval.')
    conv.consents = list(visit.consents)  # current consent, checked on every request and scheduled touch
    return chat.attach(conv, visit)


def save(conn, conv):
    conn.execute('update app.followups set conversation = %s, updated_at = now() where id = %s',
                 (Jsonb(conv.model_dump(mode='json')), conv.id))


def invite(conn, row):
    """Rotate the one-use code. The plaintext is returned once to the signed-in clinician."""
    code = secrets.token_hex(16)
    conn.execute('update app.followups set join_hash = %s, join_expires_at = now() + interval \'24 hours\' '
                 'where id = %s', (sha256(code.encode()).hexdigest(), row['id']))
    return 'JOIN ' + code


def public_view(conn, row, configured=False):
    conv = restore(conn, row)
    receipts = all_rows(conn, 'select message_ref, status, updated_at from app.whatsapp_receipts where followup_id = %s',
                        (row['id'],))
    return {'conversation': conv.model_dump(mode='json'), 'whatsapp_configured': configured,
            'channel': conv.plan.channel, 'delivery': 'stopped' if conv.stopped else
            'waiting_for_patient' if not conv.contact else 'connected',
            'receipts': [{**r, 'updated_at': r['updated_at'].isoformat()} for r in receipts],
            'deliveries':deliveries(conn,row['id'])}


class FollowupService:
    def __init__(self, settings, channel=AUTO, speech=AUTO, nlu=AUTO, reader=AUTO, memory=AUTO):
        self.settings = settings
        self.channel = WhatsAppChannel.from_env() if channel is AUTO else channel
        self.speech = speech_from_env() if speech is AUTO else speech
        self.memory = (SafeMemory(SupabaseMemoryStore(settings.database_url, schema='app'),
                                  LocalMemoryStore(settings.artifacts_dir / 'followup-memory'))
                       if memory is AUTO else memory)
        self.lock = threading.RLock()
        self.journey = Journey(self)
        self.clinic_reports = ClinicReports(self)
        client = None
        if nlu is AUTO or reader is AUTO:
            try:
                client = build_client(REPO_ROOT / '.env', settings.artifacts_dir / 'followup-cache',
                                      only=settings.llm_provider, quick=True)
            except ValueError:
                pass
        self.nlu = make_nlu(client, self.memory) if nlu is AUTO and client else (None if nlu is AUTO else nlu)
        if reader is AUTO:
            from ..agent.documents import read_document
            try:
                document_client=build_client(REPO_ROOT/'.env',settings.artifacts_dir/'document-cache',quick=True,timeout=30,budget=90)
            except ValueError:
                document_client=None
            self.reader = (lambda data, mime: read_document(data, mime, document_client)) if document_client else None
        else:
            self.reader = reader

    def remember(self, conv):
        records = conv.records[conv.remembered:]
        self.memory.add([i for r in records for i in items_from_record(conv, r)])
        conv.remembered = len(conv.records)

    def message(self, conn, row, text=None, button=None):
        conv = restore(conn, row)
        if conv.superseded:
            raise GateRefused('A newer visit is active for this patient.')
        if conv.plan.channel != 'simulated':
            raise GateRefused('Replies to a WhatsApp conversation must come from its bound phone.')
        if not self.journey.command(conn,conv,text=text,button=button):
            chat.receive(conv, text=text, button=button, nlu=self.nlu)
        menu(conv)
        self.remember(conv)
        save(conn, conv)
        return public_view(conn, {**row, 'conversation': conv.model_dump(mode='json')}, self.channel is not None)

    def document(self, conn, row, data, mime):
        conv = restore(conn, row)
        if conv.superseded or conv.stopped:
            raise GateRefused('This conversation is stopped or a newer visit is active.')
        if conv.plan.channel != 'simulated':
            raise GateRefused('Reports for this WhatsApp conversation must come from its bound phone.')
        self.journey.upload(conn,conv,data,mime)
        self.remember(conv)
        save(conn, conv)
        return public_view(conn, {**row, 'conversation': conv.model_dump(mode='json')}, self.channel is not None)

    def enqueue(self, conn, payload):
        messages, calls = parse_webhook(payload)
        # Signed-event diagnostics contain no message text, raw number, invitation or credential.
        # Distinguish missing Meta forwarding from a local recipient filter without storing a rejected sender.
        audit(conn, None, None, 'whatsapp.webhook_received', 'whatsapp', None,
              {'messages': len(messages), 'allowed': sum(self.channel.allowed(m.sender) for m in messages),
               'kinds': [m.kind for m in messages], 'sender_lengths': [len(m.sender) for m in messages],
               'receipt_count': sum(len(change.get('value', {}).get('statuses', []))
                                    for entry in payload.get('entry', []) for change in entry.get('changes', []))})
        if calls:
            # Calling needs its own long-lived media service. Never silently accept a call we cannot answer.
            raise GateRefused('WhatsApp calling is not enabled on the doctor workspace endpoint.')
        count = 0
        for item in messages:
            if not item.message_id or not self.channel.allowed(item.sender):
                continue
            data = asdict(item)
            data['sender'] = self.channel.contact(item.sender)
            invitation = JOIN.fullmatch(item.text or '') if item.kind == 'text' else None
            if invitation:
                data['join_hash'] = sha256(invitation.group(1).encode()).hexdigest()
                data['text'] = None
            inserted=one(conn,'insert into app.whatsapp_events (id, payload) values (%s,%s) on conflict do nothing returning id',
                         (item.message_id, Jsonb(data)))
            if inserted:
                self.clinic_reports.touch(conn,data)
            count += 1
        # Receipt updates are signed too, and can never promote accepted to delivered without Meta's event.
        ranks = {'accepted': 0, 'sent': 1, 'delivered': 2, 'read': 3, 'failed': 4}
        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                for receipt in change.get('value', {}).get('statuses', []):
                    self.clinic_reports.receipt(conn,receipt)
                    row = one(conn, 'select * from app.whatsapp_receipts where message_id = %s for update',
                              (receipt.get('id'),))
                    status = receipt.get('status')
                    if row and status in ranks and ranks[status] >= ranks.get(row['status'], 0):
                        conn.execute('update app.whatsapp_receipts set status = %s, updated_at = now() '
                                     'where message_id = %s', (status, row['message_id']))
                        if status in ('delivered','read','failed'):
                            conn.execute('update app.patient_deliveries set state=%s,updated_at=now() where provider_id=%s',
                                         (status,row['message_id']))
        return count

    def _deliver(self, conn, conv):
        channel = self.channel
        if not channel or not conv.contact:
            return
        number = next((n for n in channel.config.test_numbers if channel.contact(n) == conv.contact), None)
        if not number or not conv.last_inbound_at or now() - conv.last_inbound_at > timedelta(hours=24):
            return
        for index in range(conv.delivered, len(conv.messages)):
            message = conv.messages[index]
            if conv.stopped and message.kind != 'system':
                conv.delivered = index + 1
                continue
            if message.sender == 'clinic':
                result = channel._send(number, message)
                for sent in (result or {}).get('messages', []):
                    conn.execute('insert into app.whatsapp_receipts (message_id, followup_id, message_ref) '
                                 'values (%s,%s,%s) on conflict do nothing', (sent['id'], conv.id, message.id))
            conv.delivered = index + 1

    def activate_report(self,conn,item,source):
        """A signed report button selects context without binding a shared test phone to another identity."""
        row=one(conn,'select * from app.followups where encounter_id=%s and version=%s for update',
                (source['encounter_id'],source['version']))
        expected=one(conn,'select expected_contact from app.patient_contact_requests where patient_id='
                     '(select patient_id from app.encounters where id=%s) and organisation_id=%s',
                     (source['encounter_id'],source['organisation_id']))
        if not row or not expected or expected['expected_contact']!=item['sender']:
            raise GateRefused('This report is not registered for the requesting phone.')
        conv=restore(conn,row)
        if conv.stopped:
            raise GateRefused('Renew follow-up consent with the clinic before restarting.')
        window=one(conn,'select opted_out_at from app.whatsapp_contact_windows where contact=%s',(item['sender'],))
        if window and window['opted_out_at']:
            raise GateRefused('This phone stopped WhatsApp follow-up.')
        for previous in all_rows(conn,"select * from app.followups where conversation->>'contact'=%s and id<>%s for update",
                                 (item['sender'],row['id'])):
            old=Conversation.model_validate(previous['conversation']);old.superseded=True;save(conn,old)
        conv.superseded=False;conv.contact=item['sender'];conv.last_inbound_at=now();conv.plan.channel='whatsapp'
        conv.clock=now()-chat.STEP;conv.delivered=len(conv.messages)
        self.channel.graph.send_text(next(number for number in self.channel.config.test_numbers
                                          if self.channel.contact(number)==item['sender']),
            f'Active patient: {conv._visit.approved.header.patient_name}. Visit {conv._visit.approved.header.visit_date}. '
            'Questions and uploaded reports in this chat will be saved to this patient’s doctor dashboard. '
            'Use Patient menu under another report to switch patients.')
        chat.receive(conv,button='lang_'+conv.language)
        if not any(message.buttons for message in conv.messages[conv.delivered:]):
            chat.receive(conv,text='HELLO')
        menu(conv);self.remember(conv);self._deliver(conn,conv);save(conn,conv)
        conn.execute('insert into app.whatsapp_active_reports(contact,followup_id) values(%s,%s) '
                     'on conflict(contact) do update set followup_id=excluded.followup_id,updated_at=now()',
                     (item['sender'],conv.id))
        audit(conn,None,conv.clinic_id,'followup.report_selected','followup',conv.id,{'event_id':item['message_id']})

    def handle(self, conn, event):
        item = event['payload']
        if self.clinic_reports.receive(conn,item):
            return
        contact = item['sender']
        joining = item.get('join_hash')
        if joining:
            row = one(conn, 'select * from app.followups where join_hash = %s and join_expires_at > now() for update',
                      (joining,))
            if row is None:
                return
            conv = restore(conn, row)
            if conv.stopped or (conv.contact and conv.contact != contact):
                return
            # One test phone has one active visit. A newer join disables sending on its previous visit.
            previous = all_rows(conn, "select * from app.followups where conversation->>'contact' = %s and id <> %s for update",
                                (contact, row['id']))
            for old in previous:
                stored = Conversation.model_validate(old['conversation'])
                stored.superseded = True
                save(conn, stored)
            conv.plan.channel, conv.contact = 'whatsapp', contact
            conv.delivered = 0
            conn.execute('update app.followups set join_hash = null, join_expires_at = null where id = %s', (conv.id,))
        else:
            row=one(conn,'select f.* from app.followups f join app.whatsapp_active_reports a on a.followup_id=f.id '
                    "where a.contact=%s and f.conversation->>'stopped'='false' for update of f",(contact,))
            if row is None:
                row = one(conn, "select f.* from app.followups f join app.encounters e on e.id=f.encounter_id "
                      "where f.conversation->>'contact' = %s and f.conversation->>'stopped' = 'false' "
                      "and coalesce(f.conversation->>'superseded','false')='false' "
                      "order by e.visit_date desc,e.created_at desc,f.version desc limit 1 for update of f", (contact,))
            if row is None:
                return
            conv = restore(conn, row)
        conv.last_inbound_at, conv.last_inbound_voice = now(), item['kind'] == 'audio'
        scoped=one(conn,'select followup_id from app.whatsapp_active_reports where contact=%s and followup_id=%s',(contact,conv.id))
        if not scoped:
            link_channel(conn,conv)
        conn.execute("update app.patient_deliveries set not_before=now() where followup_id=%s and state in ('waiting_for_contact','waiting_for_window')",(conv.id,))
        if not joining:
            # The core has a controllable demo clock; live messages retain their wall-clock receipt time.
            conv.clock = now() - chat.STEP
            if item['kind'] == 'text':
                if not self.journey.command(conn,conv,text=(item.get('text') or '')[:2000]):
                    chat.receive(conv, text=(item.get('text') or '')[:2000], nlu=self.nlu)
            elif item['kind'] == 'button':
                if not self.journey.command(conn,conv,button=item.get('button')):
                    chat.receive(conv, button=item.get('button'))
            elif item['kind'] == 'audio':
                if self.speech:
                    transcribe_ogg_voice_note(conv, self.channel.graph.download_media(item['media_id']), self.speech, self.nlu,
                                              command=lambda text:self.journey.command(conn,conv,text=text,source='prisma'))
                else:
                    chat.voice_not_used(conv)
            elif item['kind'] in ('image', 'document'):
                self.journey.upload(conn,conv,self.channel.graph.download_media(item['media_id']),item.get('mime') or '')
        menu(conv)
        if conv.stopped:
            conn.execute('update app.whatsapp_contact_windows set opted_out_at=now() where contact=%s',(contact,))
            conn.execute('update app.clinic_report_contacts set opted_out_at=now() where contact=%s',(contact,))
            conn.execute("update app.clinic_report_jobs set state='cancelled',error='Recipient stopped reports',updated_at=now() "
                         "where recipient=%s and state in ('pending','waiting_for_window','waiting_for_artifact')",(contact,))
            conn.execute('update app.patient_channels set opted_out_at=now() where patient_id=%s and organisation_id=%s',
                         (conv.patient_id,conv.clinic_id))
            conn.execute("update app.patient_deliveries set state='cancelled',error='Patient stopped follow-up',updated_at=now() "
                         "where followup_id=%s and state not in ('accepted','delivered','read','failed','cancelled')",(conv.id,))
        self.remember(conv)
        self._deliver(conn, conv)
        save(conn, conv)
        audit(conn, None, row['organisation_id'], 'followup.received', 'followup', conv.id,
              {'event_id': event['id'], 'kind': item['kind']})

    def tick(self):
        if not self.channel:
            return False
        with self.lock, transaction() as conn:
            event = one(conn, "select * from app.whatsapp_events where state = 'pending' and not_before <= now() "
                        "order by updated_at limit 1 for update skip locked")
            if event:
                try:
                    with conn.transaction():
                        self.handle(conn, event)
                except GateRefused:
                    conn.execute("update app.whatsapp_events set state = 'done', error = 'consent_or_report_unavailable' where id = %s",
                                 (event['id'],))
                    return True
                except Exception as error:
                    attempts = event['attempts'] + 1
                    conn.execute("update app.whatsapp_events set state = %s, attempts = %s, error = %s, "
                                 "not_before = now() + interval '1 minute', updated_at = now() where id = %s",
                                 ('failed' if attempts >= 3 else 'pending', attempts, type(error).__name__, event['id']))
                    log.warning('follow-up event failed: %s', type(error).__name__)
                    return True
                conn.execute("update app.whatsapp_events set state = 'done', attempts = attempts + 1, updated_at = now() where id = %s",
                             (event['id'],))
                return True
        return self.clinic_reports.tick() or self.journey.tick() or self.scheduled()

    def scheduled(self):
        with self.lock, transaction() as conn:
            rows = all_rows(conn, "select * from app.followups where conversation->>'contact' is not null "
                            "and conversation->>'stopped' = 'false' order by updated_at for update skip locked")
            for row in rows:
                try:
                    conv = restore(conn, row)
                except GateRefused:
                    continue
                if conv.superseded:
                    continue
                if not conv.language_chosen or not conv.last_inbound_at or now() - conv.last_inbound_at > timedelta(hours=24):
                    continue
                pending = [t for t in conv.plan.touches if t.status == 'planned' and t.kind != 'summary']
                if pending and min(t.due_at for t in pending) <= now():
                    local = now().astimezone(pending[0].due_at.tzinfo)
                    if not 9 <= local.hour < 20:
                        continue
                    chat.advance(conv)
                    self._deliver(conn, conv)
                    save(conn, conv)
                    return True
        return False


def tasks_for(conn, organisation_id):
    rows = all_rows(conn, 'select * from app.followups where organisation_id = %s', (organisation_id,))
    tasks = []
    for row in rows:
        conv = Conversation.model_validate(row['conversation'])
        tasks.extend({**t.model_dump(mode='json'), 'followup_id': row['id'], 'encounter_id': row['encounter_id'],
                      'patient_name': conv.patient_name} for t in conv.tasks if t.status == 'open')
    return sorted(tasks, key=lambda t: (TASK_ORDER.index(t['kind']), t['created_at']))
