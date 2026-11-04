"""Doctor routes use the existing session, CSRF and organisation boundary; Meta uses HMAC."""
import json

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse
from fastapi.responses import Response
from hashlib import sha256
from urllib.parse import quote
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..agent.gate import CONSENT, GateRefused
from ..agent import conversation as chat
from ..agent.whatsapp import digits, verify_signature
from ..agent.prescription_audio import LANGUAGES
from ..contracts.followup import Conversation
from ..agent.documents import MAX_BYTES as DOCUMENT_BYTES
from . import auth
from .db import audit, one, transaction
from .followup import context, initialize, invite, public_view, restore, save, tasks_for
from .repo import get_encounter, get_patient
from .journey import history
from .config import read_env

WEBHOOK = '/whatsapp/webhook'
MAX_WEBHOOK_BYTES = 1024 * 1024


class Inbound(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    button: str | None = Field(default=None, min_length=1, max_length=40)

    @model_validator(mode='after')
    def one_input(self):
        if (self.text is None) == (self.button is None):
            raise ValueError('Send either text or a button.')
        return self


class ConsentChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool


class PatientContact(BaseModel):
    model_config=ConfigDict(extra='forbid')
    phone: str = Field(min_length=8,max_length=24)
    language: str
    consent_confirmed: bool


def install(app, state, session_of, ApiError):
    def scoped(conn, session, encounter_id, lock=False):
        encounter = get_encounter(conn, session['organisation_id'], encounter_id, lock=lock)
        if encounter is None:
            raise ApiError(404, 'not_found', 'That visit was not found.')
        return encounter

    def row_for(conn, encounter):
        return one(conn, 'select * from app.followups where encounter_id = %s and version = %s for update',
                   (encounter['id'], encounter['approved_version']))

    def service():
        return state['followup']

    @app.get('/api/v1/patients/{patient_id}/journey')
    def patient_journey(request: Request, patient_id: str):
        session=session_of(request);auth.require(session,'resolve')
        with transaction() as conn:
            if get_patient(conn,session['organisation_id'],patient_id) is None:
                raise ApiError(404,'not_found','That patient was not found.')
            return history(conn,session['organisation_id'],patient_id)

    @app.post('/api/v1/patients/{patient_id}/whatsapp-target')
    def set_patient_contact(request: Request, patient_id: str, body: PatientContact):
        session=session_of(request);auth.require(session,'resolve')
        channel=service().channel
        if not body.consent_confirmed:
            raise ApiError(422,'consent_required','Confirm the patient agreed to WhatsApp delivery.')
        if body.language not in LANGUAGES:
            raise ApiError(422,'unsupported_language','Choose Hindi, English, Tamil, Telugu or Gujarati.')
        number=digits(body.phone)
        if not channel or not channel.allowed(number):
            raise ApiError(422,'recipient_not_enabled','This private test server can use only its configured WhatsApp test recipients.')
        contact=channel.contact(number)
        with transaction() as conn:
            patient=get_patient(conn,session['organisation_id'],patient_id)
            if patient is None:
                raise ApiError(404,'not_found','That patient was not found.')
            if not patient['synthetic']:
                raise ApiError(409,'synthetic_only','This prototype accepts synthetic visits only.')
            old=one(conn,'select * from app.patient_channels where contact=%s or patient_id=%s for update',(contact,patient_id))
            if old and (old['patient_id']!=patient_id or old['organisation_id']!=session['organisation_id'] or old['contact']!=contact):
                raise ApiError(409,'contact_conflict','This contact is linked to another patient, or this patient has a different verified contact. Reconcile with the clinic.')
            conn.execute('insert into app.patient_contact_requests(patient_id,organisation_id,expected_contact) values(%s,%s,%s) '
                         'on conflict(patient_id) do update set expected_contact=excluded.expected_contact,updated_at=now()',
                         (patient_id,session['organisation_id'],contact))
            conn.execute('update app.patients set language_pref=%s,consents=array_append(array_remove(consents,%s),%s) where id=%s',
                         (body.language,CONSENT,CONSENT,patient_id))
            audit(conn,session['user_id'],session['organisation_id'],'patient.whatsapp_target','patient',patient_id,
                  {'language':body.language,'consent':True,'verified':bool(old)})
            return {'linked':bool(old),'needs_patient_join':not bool(old),'language':body.language}

    @app.get('/api/v1/patient-uploads/{upload_id}/download')
    def original_upload(request: Request, upload_id: str):
        session=session_of(request);auth.require(session,'resolve')
        with transaction() as conn:
            row=one(conn,'select * from app.patient_uploads where id=%s and organisation_id=%s',(upload_id,session['organisation_id']))
        if not row:
            raise ApiError(404,'not_found','That uploaded report was not found.')
        data=bytes(row['data'])
        if sha256(data).hexdigest()!=row['sha256']:
            raise ApiError(410,'file_changed','The stored report fingerprint changed.')
        ext={'application/pdf':'pdf','image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[row['mime']]
        return Response(data,media_type=row['mime'],headers={'Cache-Control':'private, no-store',
                        'Content-Disposition':f'attachment; filename="patient-report-{upload_id}.{ext}"'})

    @app.post('/api/v1/patient-uploads/{upload_id}/review')
    def review_upload(request: Request, upload_id: str):
        session=session_of(request);auth.require(session,'resolve')
        with transaction() as conn:
            row=one(conn,'update app.patient_uploads set reviewed_by=%s,reviewed_at=now() where id=%s and organisation_id=%s returning id',
                    (session['user_id'],upload_id,session['organisation_id']))
            if not row:
                raise ApiError(404,'not_found','That uploaded report was not found.')
            audit(conn,session['user_id'],session['organisation_id'],'patient_upload.reviewed','upload',upload_id)
            return {'ok':True}

    @app.post('/api/v1/encounters/{encounter_id}/followup/consent')
    def consent(request: Request, encounter_id: str, body: ConsentChange):
        session = session_of(request)
        auth.require(session, 'resolve')
        with transaction() as conn:
            encounter = scoped(conn, session, encounter_id, lock=True)
            patient = get_patient(conn, session['organisation_id'], encounter['patient_id'])
            if not patient['synthetic']:
                raise ApiError(409, 'synthetic_only', 'Only synthetic follow-up is supported.')
            conn.execute('update app.patients set consents = array_remove(consents, %s) where id = %s',
                         (CONSENT, patient['id']))
            if body.enabled:
                conn.execute('update app.patients set consents = array_append(consents, %s) where id = %s',
                             (CONSENT, patient['id']))
            audit(conn, session['user_id'], session['organisation_id'], 'followup.consent', 'patient', patient['id'],
                  {'enabled': body.enabled, 'synthetic': True})
            return {'enabled': body.enabled}

    @app.get('/api/v1/encounters/{encounter_id}/followup')
    def followup_view(request: Request, encounter_id: str):
        session = session_of(request)
        auth.require(session, 'resolve')
        with transaction() as conn:
            encounter = scoped(conn, session, encounter_id)
            row = row_for(conn, encounter)
            if row is None:
                try:
                    context(conn, encounter_id)
                except GateRefused as error:
                    return {'conversation': None, 'reason': str(error), 'whatsapp_configured': service().channel is not None}
                return {'conversation': None, 'reason': 'Follow-up has not started.',
                        'whatsapp_configured': service().channel is not None}
            try:
                return public_view(conn, row, service().channel is not None)
            except GateRefused as error:
                return {'conversation': None, 'reason': str(error), 'whatsapp_configured': service().channel is not None}

    @app.post('/api/v1/encounters/{encounter_id}/followup')
    def start_followup(request: Request, encounter_id: str):
        session = session_of(request)
        auth.require(session, 'resolve')
        with transaction() as conn:
            encounter = scoped(conn, session, encounter_id, lock=True)
            try:
                visit = context(conn, encounter_id)
                patient = get_patient(conn, session['organisation_id'], encounter['patient_id'])
                row = initialize(conn, encounter, visit.approved, patient)
                result = public_view(conn, row, service().channel is not None)
                if result['conversation']['stopped']:
                    raise GateRefused('The patient stopped this follow-up. Obtain renewed consent for a new visit.')
                result['join_command'] = invite(conn, row)
                sender=digits(read_env().get('WHATSAPP_SENDER_NUMBER',''))
                result['join_url']='https://wa.me/'+sender+'?text='+quote(result['join_command']) if sender else None
            except GateRefused as error:
                raise ApiError(409, 'followup_unavailable', str(error)) from None
            audit(conn, session['user_id'], session['organisation_id'], 'followup.invited', 'encounter', encounter_id)
            return result

    @app.post('/api/v1/encounters/{encounter_id}/followup/messages')
    def simulated_reply(request: Request, encounter_id: str, body: Inbound):
        session = session_of(request)
        auth.require(session, 'resolve')
        with service().lock, transaction() as conn:
            encounter = scoped(conn, session, encounter_id, lock=True)
            row = row_for(conn, encounter)
            if row is None:
                raise ApiError(409, 'followup_unavailable', 'Start follow-up first.')
            try:
                return service().message(conn, row, text=body.text, button=body.button)
            except GateRefused as error:
                raise ApiError(409, 'followup_unavailable', str(error)) from None

    @app.get('/api/v1/followup/tasks')
    def doctor_tasks(request: Request):
        session = session_of(request)
        auth.require(session, 'resolve')
        with transaction() as conn:
            return {'items': tasks_for(conn, session['organisation_id'])}

    @app.post('/api/v1/encounters/{encounter_id}/followup/documents')
    async def upload_document(request: Request, encounter_id: str):
        session = session_of(request)
        auth.require(session, 'resolve')
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > DOCUMENT_BYTES:
                raise ApiError(413, 'too_large', 'Reports must be under 10 MB.')
            chunks.append(chunk)
        data = b''.join(chunks)
        def work():
            with service().lock, transaction() as conn:
                encounter = scoped(conn, session, encounter_id, lock=True)
                row = row_for(conn, encounter)
                if not row:
                    raise ApiError(409, 'followup_unavailable', 'Start follow-up first.')
                try:
                    return service().document(conn, row, data, request.headers.get('content-type', ''))
                except GateRefused as error:
                    raise ApiError(409, 'followup_unavailable', str(error)) from None
        return await run_in_threadpool(work)

    @app.get('/api/v1/encounters/{encounter_id}/followup/memory')
    def memory(request: Request, encounter_id: str):
        session = session_of(request)
        auth.require(session, 'resolve')
        with transaction() as conn:
            encounter = scoped(conn, session, encounter_id)
            row = row_for(conn, encounter)
            if not row:
                return {'items': [], 'documents': []}
            conv = Conversation.model_validate(row['conversation'])
            return {'items': [i.model_dump(mode='json') for i in service().memory.recent(conv.patient_key, 200)],
                    'documents': [d.model_dump(mode='json') for d in service().memory.documents(conv.patient_key)]}

    @app.post('/api/v1/encounters/{encounter_id}/followup/advance')
    def advance_simulator(request: Request, encounter_id: str):
        session = session_of(request)
        auth.require(session, 'resolve')
        with service().lock, transaction() as conn:
            encounter = scoped(conn, session, encounter_id, lock=True)
            row = row_for(conn, encounter)
            if not row:
                raise ApiError(409, 'followup_unavailable', 'Start follow-up first.')
            try:
                conv = restore(conn, row)
                if conv.plan.channel != 'simulated':
                    raise GateRefused('The demo clock is available only in the simulator.')
                advanced = chat.advance(conv)
                save(conn, conv)
                audit(conn, session['user_id'], session['organisation_id'], 'followup.simulated_advance',
                      'followup', conv.id)
                return {**public_view(conn, {**row, 'conversation': conv.model_dump(mode='json')},
                                      service().channel is not None), 'advanced': advanced}
            except GateRefused as error:
                raise ApiError(409, 'followup_unavailable', str(error)) from None

    @app.post('/api/v1/encounters/{encounter_id}/followup/tasks/{task_id}/done')
    def finish_task(request: Request, encounter_id: str, task_id: str):
        session = session_of(request)
        auth.require(session, 'resolve')
        with transaction() as conn:
            encounter = scoped(conn, session, encounter_id, lock=True)
            row = row_for(conn, encounter)
            if not row:
                raise ApiError(404, 'not_found', 'That follow-up was not found.')
            conv = Conversation.model_validate(row['conversation'])
            task = next((t for t in conv.tasks if t.id == task_id), None)
            if not task:
                raise ApiError(404, 'not_found', 'That task was not found.')
            task.status = 'done'
            save(conn, conv)
            audit(conn, session['user_id'], session['organisation_id'], 'followup.task_done', 'followup', conv.id,
                  {'task_id': task_id})
            return {'ok': True}

    @app.get(WEBHOOK)
    def verify(request: Request):
        channel = service().channel
        if channel is None:
            raise ApiError(404, 'whatsapp_off', 'WhatsApp is not configured.')
        p = request.query_params
        if p.get('hub.mode') != 'subscribe' or p.get('hub.verify_token') != channel.config.verify_token:
            raise ApiError(403, 'bad_verification', 'Webhook verification failed.')
        return PlainTextResponse(p.get('hub.challenge', ''))

    @app.post(WEBHOOK)
    async def webhook(request: Request):
        channel = service().channel
        if channel is None:
            raise ApiError(404, 'whatsapp_off', 'WhatsApp is not configured.')
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_WEBHOOK_BYTES:
                raise ApiError(413, 'too_large', 'Webhook body is too large.')
            chunks.append(chunk)
        body = b''.join(chunks)
        if not verify_signature(body, request.headers.get('x-hub-signature-256'), channel.config.app_secret):
            raise ApiError(401, 'bad_signature', 'Webhook signature failed.')
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict) or payload.get('object') != 'whatsapp_business_account':
                raise ValueError()
            # Ignore other businesses even when they use the same Meta application secret.
            for entry in payload.get('entry', []):
                for change in entry.get('changes', []):
                    if change.get('value', {}).get('metadata', {}).get('phone_number_id') != channel.config.phone_number_id:
                        raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ApiError(400, 'bad_webhook', 'Unrecognized WhatsApp event.') from None

        def persist():
            with transaction() as conn:
                try:
                    return service().enqueue(conn, payload)
                except GateRefused as error:
                    raise ApiError(409, 'calling_unavailable', str(error)) from None
                except (ValueError, TypeError, AttributeError):
                    raise ApiError(400, 'bad_webhook', 'Unrecognized WhatsApp event.') from None
        return {'ok': True, 'queued': await run_in_threadpool(persist)}
