"""The doctor workspace: the API under /api/v1 and the web app at /. From services/api:

    uvicorn voicerx.app.main:app --host 127.0.0.1 --port 8000
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
import logging
import tempfile
import threading
import uuid
from pathlib import Path

import yaml
from fastapi import FastAPI, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from psycopg.types.json import Jsonb

from ..approve import ApprovalBlocked, HashMismatch, approve
from ..exports.patient_box import build_patient_box
from ..exports.pdf.render import html_to_pdf, render_html
from ..reference import load_reference
from ..resolve import ResolutionRefused, resolve
from ..standard import load_rules, standard_for
from ..speech.prisma import LANGUAGE_CODES, RATE, decode_audio
from . import auth, knowledge
from .clinical import initial_steps
from .config import REPO_ROOT, load_settings, today_in
from .db import all_rows, audit, close_pool, one, open_pool, transaction
from .repo import (approval_of, artifacts_of, encounters_of, get_encounter, get_patient, list_patients, parse_report,
                   patient_summary, report_row)
from ..pipeline.assemble import product_label
from .catalog import FORMS, parse_composition
from .catalog import standing
from .pharmacy import StockFileError, annotate_view, import_stock, load_stock, summary as pharmacy_summary
from .suggest import catalog_product, clinic_index, composition_text, entry_form, heard_key, shared_index
from .views import CorrectionRefused, build_resolutions, report_view
from .worker import TEMPLATES, Worker, is_adult, save_shortlist, shortlist_for
from .followup import FollowupService, initialize as initialize_followup
from .followup_routes import install as install_followup_routes
from .clinic_reports import deliveries as clinic_deliveries
from .workspace import install as install_workspace
from .private_access import authenticate
from .audio_uploads import install as install_audio_uploads
from ..agent.gate import GateRefused

log = logging.getLogger('voicerx.app')
WEB = Path(__file__).resolve().parents[2] / 'web'
MAX_SOURCE_CHARS = 20000
MAX_AUDIO_BYTES = 40 * 1024 * 1024
MAX_AUDIO_SECONDS = 20 * 60
AUDIO_TYPES = {'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/wave': 'wav',
               'audio/mpeg': 'mp3', 'audio/mp4': 'm4a', 'audio/x-m4a': 'm4a', 'audio/aac': 'aac'}
REFERENCE = load_reference(REPO_ROOT)
state = {}


class ApiError(Exception):
    def __init__(self, status, code, message, retryable=False, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.retryable, self.extra = status, code, message, retryable, extra


def warm_up():
    try:
        knowledge.warm_up()
        with transaction() as conn:
            shared_index(conn, REFERENCE.products)
    except Exception:
        log.exception('warm-up failed; the first search will load instead')


@asynccontextmanager
async def lifespan(app):
    settings = load_settings()
    state['settings'] = settings
    open_pool(settings.database_url)
    state['followup'] = FollowupService(settings)
    worker = Worker(settings, followup=state['followup'])
    state['worker'] = worker
    from .config import read_env
    if read_env().get('APP_RUN_WORKER','1')=='1':
        worker.start()
    # Load the embedding model and the product name index in the background, so the first search isn't slow.
    threading.Thread(target=warm_up, daemon=True).start()
    yield
    worker.stop()
    close_pool()


app = FastAPI(title='ARDAI doctor workspace', lifespan=lifespan, docs_url=None, redoc_url=None,openapi_url=None)


def error_body(code, message, retryable=False, correlation_id=None, **extra):
    return {'error': {'code': code, 'message': message, 'retryable': retryable, **extra}, 'correlation_id': correlation_id}


@app.exception_handler(ApiError)
async def api_error(request, error):
    return JSONResponse(error_body(error.code, error.message, error.retryable, request.state.correlation_id, **error.extra),
                        status_code=error.status)


@app.exception_handler(auth.NotSignedIn)
async def not_signed_in(request, error):
    return JSONResponse(error_body('not_signed_in', 'Please sign in again.', False, request.state.correlation_id),
                        status_code=401)


@app.exception_handler(auth.Forbidden)
async def forbidden(request, error):
    return JSONResponse(error_body('forbidden', str(error), False, request.state.correlation_id), status_code=403)


@app.exception_handler(Exception)
async def unexpected(request, error):
    log.exception('unhandled error %s', request.state.correlation_id)
    return JSONResponse(error_body('internal', 'Something went wrong. Try again.', True, request.state.correlation_id),
                        status_code=500)


@app.middleware('http')
async def headers(request: Request, call_next):
    request.state.correlation_id = uuid.uuid4().hex[:16]
    from .config import read_env
    protected=read_env().get('APP_PRIVATE_WORKSPACE')=='1'
    public_api={'/api/v1/auth/login','/api/v1/auth/options','/api/v1/health'}
    private_path=request.url.path.startswith('/static/') or request.url.path=='/v1' or (
        request.url.path.startswith('/api/v1/') and request.url.path not in public_api)
    if protected and request.url.path in ('/api/v1/auth/dev-users','/api/v1/auth/dev-login') and not state['settings'].dev_login:
        response=JSONResponse({'error':{'code':'not_found','message':'Not found.'}},status_code=404)
    elif protected and private_path:
        try:
            if not request.cookies.get(auth.COOKIE):
                raise auth.NotSignedIn()
            request.state.auth_session=await run_in_threadpool(load_request_session,request.cookies.get(auth.COOKIE))
        except auth.NotSignedIn:
            response=JSONResponse({'error':{'code':'not_signed_in','message':'Sign in required.'}},status_code=401)
        else:
            response=await call_next(request)
    else:
        response = await call_next(request)
    response.headers['X-Correlation-ID'] = request.state.correlation_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; media-src 'self' blob:; frame-ancestors 'none'; "
        "base-uri 'none'")
    # The microphone is for this page only, never for anything it embeds.
    response.headers['Permissions-Policy'] = 'microphone=(self), camera=(), geolocation=()'
    response.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
    if request.url.scheme=='https':
        response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    if protected:
        response.headers['Cache-Control']='private, no-store'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    elif request.url.path.startswith('/static/'):
        # Revalidate each load, so a changed script is never served stale from the browser cache.
        response.headers['Cache-Control'] = 'no-cache'
    if protected:
        response.headers['Cache-Control']='private, no-store'
    return response


def load_request_session(token):
    if not token or len(token)>128:
        raise auth.NotSignedIn()
    with transaction() as conn:
        return auth.load_session(conn,token)


def session_of(request):
    settings = state['settings']
    token=request.cookies.get(auth.COOKIE)
    if not token or len(token)>128:
        raise auth.NotSignedIn()
    # Shared only within this HTTP request. Every new request checks revocation and membership afresh.
    session=getattr(request.state,'auth_session',None)
    if session is None:
        session=load_request_session(token)
        request.state.auth_session=session
    auth.check_request(session, request.method, request.headers.get('X-CSRF-Token'), request.headers.get('Origin'),
                       settings.allowed_origins)
    return session


def actor(session):
    return {'id': session['user_id'], 'display_name': session['display_name']}


def not_found(what='record'):
    return ApiError(404, 'not_found', f'That {what} was not found.')


# ---------- Identity ----------

@app.get('/api/v1/health')
def health():
    return {'ok': True}


@app.get('/api/v1/auth/options')
def auth_options():
    from .config import read_env
    return {'dev_login': state['settings'].dev_login, 'password_login':read_env().get('APP_PRIVATE_WORKSPACE')=='1'}


@app.get('/api/v1/auth/dev-users')
def dev_users():
    if not state['settings'].dev_login:
        raise not_found('page')
    with transaction() as conn:
        rows = all_rows(conn, '''select u.id, u.display_name, u.specialty, o.name as organisation_name, m.role
                                 from app.users u join app.memberships m on m.user_id = u.id
                                 join app.organisations o on o.id = m.organisation_id
                                 where u.synthetic and o.synthetic order by u.display_name''')
    return {'users': rows}


@app.post('/api/v1/auth/dev-login')
async def dev_login(request: Request):
    settings = state['settings']
    if not settings.dev_login:
        raise not_found('page')
    origin = request.headers.get('Origin')
    if origin and origin not in settings.allowed_origins:
        raise auth.Forbidden('request from an origin that is not allowed')
    body = await request.json()
    with transaction() as conn:
        # Development sign-in only reaches synthetic doctors in synthetic organisations (runbook D-105).
        member = one(conn, '''select m.user_id, m.organisation_id from app.memberships m
                              join app.users u on u.id = m.user_id join app.organisations o on o.id = m.organisation_id
                              where m.user_id = %s and u.synthetic and o.synthetic''', (str(body.get('user_id')),))
        if member is None:
            raise ApiError(422, 'unknown_user', 'Choose one of the listed synthetic doctors.')
        token = auth.create_session(conn, member['user_id'], member['organisation_id'])
        session = auth.load_session(conn, token)
        audit(conn, member['user_id'], member['organisation_id'], 'session.dev_login', 'user', member['user_id'])
    response = JSONResponse(auth.session_view(session))
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite='lax', secure=request.url.scheme == 'https',
                        max_age=int(auth.LIFETIME.total_seconds()), path='/')
    return response


@app.post('/api/v1/auth/login')
async def password_login(request:Request):
    origin=request.headers.get('Origin')
    if origin and origin not in state['settings'].allowed_origins and origin!=str(request.base_url).rstrip('/'):
        raise auth.Forbidden('Request origin is not allowed.')
    if request.headers.get('content-type','').split(';')[0]!='application/json':
        raise ApiError(415,'invalid_request','Send a JSON sign-in request.')
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>4096:
            raise ApiError(413,'invalid_request','Sign-in request too large.')
    import json
    try:
        body=json.loads(data)
        username=body.get('username','');password=body.get('password','')
        if not isinstance(username,str) or not isinstance(password,str) or len(username)>120 or len(password)>200:
            raise ValueError()
    except (ValueError,AttributeError):
        raise ApiError(400,'invalid_request','Invalid sign-in request.') from None
    with transaction() as conn:
        account,limited=authenticate(conn,username,password,request.client.host if request.client else 'unknown')
        if account:
            token=auth.create_session(conn,account['user_id'],account['organisation_id'],operator_id=account['user_id'])
            current=auth.load_session(conn,token)
            audit(conn,account['user_id'],account['organisation_id'],'auth.login','account',None,{'shared_demo_account':True})
    if not account:
        raise ApiError(429 if limited else 401,'sign_in_failed','Sign-in failed. Try again later.' if limited else 'Invalid username or password.')
    response=JSONResponse(auth.session_view(current))
    response.set_cookie(auth.COOKIE,token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=7200,path='/')
    return response


@app.post('/api/v1/auth/logout')
def logout(request: Request):
    session_of(request)
    with transaction() as conn:
        auth.end_session(conn, request.cookies.get(auth.COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(auth.COOKIE, path='/')
    return response


@app.get('/api/v1/me')
def me(request: Request):
    return auth.session_view(session_of(request))


# ---------- Patients ----------

@app.get('/api/v1/patients')
def patients(request: Request, q: str = '', which: str = Query('all', alias='list'), doctor_id:str|None=None):
    session = session_of(request)
    today = today_in(session['timezone'])
    with transaction() as conn:
        rows = list_patients(conn, session['organisation_id'], q[:80], which == 'today', today,doctor_id)
    return {'items': [patient_summary(r) for r in rows], 'as_of': datetime.now(timezone.utc).isoformat(),
            'today': today.isoformat()}


@app.get('/api/v1/patients/{patient_id}')
def patient_detail(request: Request, patient_id: str):
    session = session_of(request)
    with transaction() as conn:
        patient = get_patient(conn, session['organisation_id'], patient_id)
        if patient is None:
            raise not_found('patient')
        encounters = []
        for e in encounters_of(conn, patient_id):
            latest = report_row(conn, e['id'])
            report = latest['report'] if latest else None
            encounters.append({
                'id': e['id'], 'visit_date': e['visit_date'].isoformat(), 'state': e['state'],
                'clinician_name': e['clinician_name'], 'current_version': e['current_version'],
                'approved_version': e['approved_version'], 'run_id': e['run_id'], 'run_state': e['run_state'],
                'diagnoses': [l['text'] for l in report['sections'].get('diagnoses', [])] if report else [],
                'complaints': [l['text'] for l in report['sections'].get('chief_complaints', [])] if report else [],
                'blocking': sum(i['severity'] == 'block' for i in report['issues']) if report else None})
    return {'patient': {**patient_summary(patient), 'phone_on_file': bool(patient['phone'] or patient.get('phone_encrypted')),
                        'phone_last4':patient.get('phone_last4'),
                        'consents': list(patient['consents'])}, 'encounters': encounters}


@app.get('/api/v1/patients/{patient_id}/samples')
def samples(request: Request, patient_id: str):
    """Synthetic consultation scripts written for this patient, to try the workflow without dictating."""
    session = session_of(request)
    with transaction() as conn:
        if get_patient(conn, session['organisation_id'], patient_id) is None:
            raise not_found('patient')
    items = []
    for path in sorted((REPO_ROOT / 'data/eval/cases').glob('*.yaml')):
        family = yaml.safe_load(path.read_text(encoding='utf-8'))
        if family['patient_id'] != patient_id:
            continue
        for encounter in family['encounters']:
            for variant in encounter['variants']:
                items.append({'id': variant['variant_id'], 'language': family['language'],
                              'text': '\n'.join(u['text'] for u in variant['utterances'])})
    return {'items': items}


# ---------- Encounters, sources and runs ----------

@app.post('/api/v1/patients/{patient_id}/encounters', status_code=201)
def create_encounter(request: Request, patient_id: str):
    session = session_of(request)
    auth.require(session, 'capture')
    with transaction() as conn:
        if get_patient(conn, session['organisation_id'], patient_id) is None:
            raise not_found('patient')
        encounter_id = 'enc-' + uuid.uuid4().hex[:12]
        conn.execute('insert into app.encounters (id, organisation_id, patient_id, clinician_id, visit_date) '
                     'values (%s, %s, %s, %s, %s)', (encounter_id, session['organisation_id'], patient_id,
                                                      session['user_id'], today_in(session['timezone'])))
        audit(conn, session['user_id'], session['organisation_id'], 'encounter.created', 'encounter', encounter_id)
        row = get_encounter(conn, session['organisation_id'], encounter_id)
    return {'id': row['id'], 'patient_id': patient_id, 'visit_date': row['visit_date'].isoformat(), 'state': row['state']}


@app.get('/api/v1/encounters/{encounter_id}')
def encounter_detail(request: Request, encounter_id: str):
    session = session_of(request)
    with transaction() as conn:
        encounter = get_encounter(conn, session['organisation_id'], encounter_id)
        if encounter is None:
            raise not_found('visit')
        patient = get_patient(conn, session['organisation_id'], encounter['patient_id'])
        clinician = one(conn, 'select display_name from app.users where id = %s', (encounter['clinician_id'],))
        source = one(conn, 'select id, version, kind, language, text, media_type, duration_s from app.sources '
                           'where encounter_id = %s order by version desc limit 1', (encounter_id,))
        run = one(conn, 'select * from app.runs where encounter_id = %s order by created_at desc limit 1', (encounter_id,))
    if source and source['kind'] == 'audio':
        # What was said is Prisma's transcript, once the run has one.
        source = {**source, 'duration_s': float(source['duration_s']), 'text': run['transcript'] if run else None,
                  'transcript_meta': run['transcript_meta'] if run else None,
                  'audio_url': f"/api/v1/encounters/{encounter_id}/sources/{source['id']}/audio"}
    return {'id': encounter['id'], 'visit_date': encounter['visit_date'].isoformat(), 'state': encounter['state'],
            'clinician_name': clinician['display_name'], 'current_version': encounter['current_version'],
            'approved_version': encounter['approved_version'], 'patient': patient_summary(patient),
            'source': source, 'run': run_view(run) if run else None}


@app.post('/api/v1/encounters/{encounter_id}/sources', status_code=201)
async def create_source(request: Request, encounter_id: str):
    session = session_of(request)
    auth.require(session, 'capture')
    body = await request.json()
    if body.get('kind') != 'typed':
        raise ApiError(422, 'unsupported_source', 'Only typed or pasted text is supported so far; recording comes next.')
    text = body.get('text') if isinstance(body.get('text'), str) else ''
    if not text.strip():
        raise ApiError(422, 'empty_source', 'Type or paste the consultation first.')
    if len(text) > MAX_SOURCE_CHARS:
        raise ApiError(422, 'source_too_long', f'Keep the text under {MAX_SOURCE_CHARS:,} characters.')
    language = str(body.get('language') or 'unknown')[:20]
    with transaction() as conn:
        encounter = get_encounter(conn, session['organisation_id'], encounter_id, lock=True)
        if encounter is None:
            raise not_found('visit')
        if encounter['state'] not in ('open', 'failed'):
            raise ApiError(409, 'source_locked', 'This visit has already been processed.')
        version = one(conn, 'select count(*) + 1 as v from app.sources where encounter_id = %s', (encounter_id,))['v']
        source_id = 'src-' + uuid.uuid4().hex[:12]
        conn.execute('insert into app.sources (id, encounter_id, version, kind, language, text, text_sha256, created_by) '
                     "values (%s, %s, %s, 'typed', %s, %s, %s, %s)",
                     (source_id, encounter_id, version, language, text, sha256(text.encode('utf-8')).hexdigest(),
                      session['user_id']))
        audit(conn, session['user_id'], session['organisation_id'], 'source.created', 'source', source_id,
              {'chars': len(text), 'language': language})
    return {'id': source_id, 'encounter_id': encounter_id, 'version': version, 'kind': 'typed', 'language': language}


@app.post('/api/v1/encounters/{encounter_id}/sources/audio', status_code=201)
async def upload_audio(request: Request, encounter_id: str, language: str = 'hinglish'):
    """A recording from the browser or an uploaded file, as the request body. The original is kept as sent;
    the server reads its real length rather than trusting the caller."""
    session = session_of(request)
    auth.require(session, 'capture')
    media = request.headers.get('content-type', '').split(';')[0].strip().lower()
    if media not in AUDIO_TYPES:
        raise ApiError(415, 'unsupported_audio', 'Send WebM, Ogg, WAV, MP3 or M4A audio.')
    if language not in LANGUAGE_CODES:
        raise ApiError(422, 'unsupported_language', 'Choose Hinglish, Hindi, English, Tamil or Telugu.')
    if request.headers.get('X-Recording-Consent') != 'patient-agreed':
        raise ApiError(422, 'consent_required', 'Confirm that the patient agreed to this recording.')
    if int(request.headers.get('content-length') or 0) > MAX_AUDIO_BYTES:
        raise ApiError(413, 'audio_too_large', 'Recordings are limited to 40 MB.')
    data = await request.body()
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise ApiError(413 if data else 422, 'audio_too_large' if data else 'empty_audio',
                       'Recordings are limited to 40 MB.' if data else 'The recording is empty.')
    return await store_audio(session,encounter_id,media,language,data)


async def store_audio(session,encounter_id,media,language,data):
    try:
        samples = await run_in_threadpool(decode_audio, data)
    except Exception:
        raise ApiError(422, 'unreadable_audio', 'This file could not be read as audio.') from None
    seconds = len(samples) / RATE
    if seconds < 2:
        raise ApiError(422, 'audio_too_short', 'The recording is under two seconds long.')
    if seconds > MAX_AUDIO_SECONDS:
        raise ApiError(422, 'audio_too_long', 'Recordings are limited to 20 minutes.')
    with transaction() as conn:
        encounter = get_encounter(conn, session['organisation_id'], encounter_id, lock=True)
        if encounter is None:
            raise not_found('visit')
        if encounter['state'] not in ('open', 'failed'):
            raise ApiError(409, 'source_locked', 'This visit has already been processed.')
        patient = get_patient(conn, session['organisation_id'], encounter['patient_id'])
        if 'recording' not in patient['consents']:
            raise ApiError(422, 'no_recording_consent', "This patient's record has no consent to recording. Type the visit instead.")
        version = one(conn, 'select count(*) + 1 as v from app.sources where encounter_id = %s', (encounter_id,))['v']
        source_id = 'src-' + uuid.uuid4().hex[:12]
        folder = state['settings'].artifacts_dir / encounter_id / 'sources'
        folder.mkdir(parents=True, exist_ok=True)
        file_name = f'{source_id}.{AUDIO_TYPES[media]}'
        (folder / file_name).write_bytes(data)
        consent = {'patient_consent_on_file': True, 'confirmed_by': session['user_id'],
                   'confirmed_at': datetime.now(timezone.utc).isoformat(), 'method': 'confirmed by the doctor in the app'}
        conn.execute('insert into app.sources (id, encounter_id, version, kind, language, media_type, file_name, sha256, '
                     "duration_s, consent, created_by) values (%s, %s, %s, 'audio', %s, %s, %s, %s, %s, %s, %s)",
                     (source_id, encounter_id, version, language, media, file_name, sha256(data).hexdigest(),
                      round(seconds, 1), Jsonb(consent), session['user_id']))
        conn.execute('insert into app.source_files(source_id,sha256,data) values(%s,%s,%s)',(source_id,sha256(data).hexdigest(),data))
        audit(conn, session['user_id'], session['organisation_id'], 'source.audio', 'source', source_id,
              {'bytes': len(data), 'seconds': round(seconds, 1), 'media_type': media, 'language': language})
    return {'id': source_id, 'encounter_id': encounter_id, 'version': version, 'kind': 'audio', 'language': language,
            'duration_s': round(seconds, 1)}


@app.get('/api/v1/encounters/{encounter_id}/sources/{source_id}/audio')
def source_audio(request: Request, encounter_id: str, source_id: str):
    session = session_of(request)
    with transaction() as conn:
        if get_encounter(conn, session['organisation_id'], encounter_id) is None:
            raise not_found('visit')
        source = one(conn, "select * from app.sources where id = %s and encounter_id = %s and kind = 'audio'",
                     (source_id, encounter_id))
    if source is None:
        raise not_found('recording')
    path = state['settings'].artifacts_dir / encounter_id / 'sources' / source['file_name']
    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != source['sha256']:
        with transaction() as conn:
            stored=one(conn,'select data,sha256 from app.source_files where source_id=%s',(source_id,))
        if stored and stored['sha256']==source['sha256'] and sha256(bytes(stored['data'])).hexdigest()==source['sha256']:
            return Response(bytes(stored['data']),media_type=source['media_type'],headers={'Cache-Control':'private, no-store'})
        raise ApiError(410, 'recording_changed', 'This recording is missing or no longer matches its record.')
    return FileResponse(path, media_type=source['media_type'])


def run_view(row):
    return {'run_id': row['id'], 'encounter_id': row['encounter_id'], 'source_id': row['source_id'],
            'source_version': row['source_version'], 'state': row['state'], 'stage': row['stage'], 'steps': row['steps'],
            'attempts': row['attempts'], 'updated_at': row['updated_at'].isoformat(), 'draft_version': row['draft_version'],
            'error': row['error']}


@app.post('/api/v1/encounters/{encounter_id}/runs', status_code=202)
async def create_run(request: Request, encounter_id: str):
    session = session_of(request)
    auth.require(session, 'capture')
    body = await request.json()
    with transaction() as conn:
        encounter = get_encounter(conn, session['organisation_id'], encounter_id, lock=True)
        if encounter is None:
            raise not_found('visit')
        active = one(conn, "select * from app.runs where encounter_id = %s and state in ('queued', 'running', 'retry_wait') "
                           'order by created_at desc limit 1', (encounter_id,))
        if active:
            return run_view(active)
        if encounter['current_version'] is not None:
            raise ApiError(409, 'already_processed', 'This visit already has a draft. Start a new visit to process again.')
        source = one(conn, 'select * from app.sources where id = %s and encounter_id = %s and version = %s',
                     (str(body.get('source_id')), encounter_id, body.get('source_version')))
        if source is None:
            raise ApiError(422, 'unknown_source', 'That source version is not part of this visit.')
        run_id = 'run-' + uuid.uuid4().hex[:12]
        conn.execute('insert into app.runs (id, encounter_id, source_id, source_version, steps, config, created_by) '
                     'values (%s, %s, %s, %s, %s, %s, %s)',
                     (run_id, encounter_id, source['id'], source['version'], Jsonb(initial_steps(source['kind'])),
                      Jsonb({'pipeline': 'extract-v5/report-v3', 'provider': state['settings'].llm_provider}),
                      session['user_id']))
        conn.execute("update app.encounters set state = 'processing' where id = %s", (encounter_id,))
        audit(conn, session['user_id'], session['organisation_id'], 'run.queued', 'run', run_id)
        row = one(conn, 'select * from app.runs where id = %s', (run_id,))
    return run_view(row)


def run_for(conn, session, run_id):
    row = one(conn, 'select r.* from app.runs r join app.encounters e on e.id = r.encounter_id '
                    'where r.id = %s and e.organisation_id = %s', (run_id, session['organisation_id']))
    if row is None:
        raise not_found('processing run')
    return row


@app.get('/api/v1/runs/{run_id}')
def get_run(request: Request, run_id: str):
    session = session_of(request)
    with transaction() as conn:
        return run_view(run_for(conn, session, run_id))


@app.post('/api/v1/runs/{run_id}/retry', status_code=202)
def retry_run(request: Request, run_id: str):
    session = session_of(request)
    auth.require(session, 'capture')
    with transaction() as conn:
        row = run_for(conn, session, run_id)
        if row['state'] not in ('failed', 'incomplete'):
            return run_view(row)
        kind = one(conn, 'select kind from app.sources where id = %s', (row['source_id'],))['kind']
        conn.execute("update app.runs set state = 'queued', steps = %s, error = null, attempts = 0, not_before = now(), "
                     'updated_at = now() where id = %s', (Jsonb(initial_steps(kind)), run_id))
        conn.execute("update app.encounters set state = 'processing' where id = %s", (row['encounter_id'],))
        audit(conn, session['user_id'], session['organisation_id'], 'run.retried', 'run', run_id)
        return run_view(one(conn, 'select * from app.runs where id = %s', (run_id,)))


# ---------- Review, approval and artifacts ----------

def envelope(conn, session, encounter, row):
    report = parse_report(row)
    suggestions = {r['medication_id']: {'heard': r['heard'], 'items': r['suggestions']} for r in all_rows(
        conn, 'select medication_id, heard, suggestions from app.medicine_suggestions where encounter_id = %s',
        (encounter['id'],))}
    approval = approval_of(conn, encounter['id'], report.version) if report.status == 'approved' else None
    artifacts = [{**a, 'created_at': a['created_at'].isoformat(), 'updated_at': a['updated_at'].isoformat()}
                 for a in artifacts_of(conn, encounter['id'], report.version)] if approval else []
    result = report_view(report, encounter['id'], encounter['patient_id'], encounter['organisation_id'], REFERENCE.products,
                       auth.capabilities(session),
                       approval={'id': approval['id'], 'approver_id': approval['approver_id'],
                                 'approver_name': approval['approver_name'],
                                 'approved_at': approval['approved_at'].isoformat()} if approval else None,
                       artifacts=artifacts, suggestions=suggestions, rules=load_rules(REPO_ROOT))
    result['clinic_deliveries'] = clinic_deliveries(conn,encounter['id'],report.version)
    if report.status == 'draft':
        annotate_view(result, load_stock(conn, encounter['organisation_id']),
                      {**REFERENCE.products, **report.products_used})
    else:
        result['pharmacy'] = None
    return result


@app.get('/api/v1/encounters/{encounter_id}/report')
def get_report(request: Request, encounter_id: str, version: int | None = None):
    session = session_of(request)
    with transaction() as conn:
        encounter = get_encounter(conn, session['organisation_id'], encounter_id)
        if encounter is None:
            raise not_found('visit')
        row = report_row(conn, encounter_id, version)
        if row is None:
            raise ApiError(404, 'no_report', 'This visit has no report yet.')
        return envelope(conn, session, encounter, row)


def check_expected(row, body):
    if body.get('expected_version') != row['version'] or body.get('expected_content_hash') != row['content_hash']:
        raise ApiError(409, 'version_conflict', 'This draft changed. Reload and review the latest version.',
                       current_version=row['version'])


@app.post('/api/v1/encounters/{encounter_id}/resolutions')
async def post_resolutions(request: Request, encounter_id: str):
    session = session_of(request)
    auth.require(session, 'resolve')
    body = await request.json()
    with transaction() as conn:
        encounter = get_encounter(conn, session['organisation_id'], encounter_id, lock=True)
        if encounter is None:
            raise not_found('visit')
        if encounter['state'] != 'in_review':
            raise ApiError(409, 'not_in_review', 'Only a draft in review can be corrected.')
        row = report_row(conn, encounter_id, encounter['current_version'], 'draft')
        check_expected(row, body)
        draft = parse_report(row)
        try:
            corrections = build_resolutions(body.get('resolutions') or [], actor(session), datetime.now(timezone.utc))
            # A product from outside the formulary (Indian list, clinic) joins this correction's catalogue.
            products = dict(REFERENCE.products)
            for c in corrections:
                pid = c.value.get('product_id') if c.action in ('choose_product', 'add_medicine') else None
                if pid and pid not in products and pid not in draft.products_used:
                    product = catalog_product(conn, session['organisation_id'], pid, REFERENCE.products)
                    if product:
                        products[pid] = product
            updated = resolve(draft, corrections, REFERENCE.model_copy(update={'products': products}))
        except (CorrectionRefused, ResolutionRefused) as error:
            raise ApiError(422, 'correction_refused', str(error)[:300]) from None
        # Remember what this doctor meant by words that didn't match exactly; it ranks first next time.
        heard = {m.id: m.spoken_name for m in draft.checked.medications if m.match != 'exact'}
        for c in corrections:
            if c.action == 'choose_product' and c.target in heard:
                conn.execute('insert into app.medicine_aliases (organisation_id, doctor_id, heard_key, product_id) '
                             'values (%s, %s, %s, %s) on conflict (organisation_id, doctor_id, heard_key, product_id) '
                             'do update set times = app.medicine_aliases.times + 1, last_at = now()',
                             (session['organisation_id'], session['user_id'], heard_key(heard[c.target]),
                              c.value['product_id']))
        conn.execute('insert into app.report_versions (encounter_id, version, status, report, content_hash, created_by) '
                     "values (%s, %s, 'draft', %s, %s, %s)",
                     (encounter_id, updated.version, Jsonb(updated.model_dump(mode='json')), updated.content_hash,
                      session['user_id']))
        conn.execute('update app.encounters set current_version = %s where id = %s', (updated.version, encounter_id))
        audit(conn, session['user_id'], session['organisation_id'], 'draft.corrected', 'encounter', encounter_id,
              {'from_version': row['version'], 'to_version': updated.version,
               'actions': [c.action for c in corrections]})
        return envelope(conn, session, encounter, report_row(conn, encounter_id, updated.version, 'draft'))


@app.post('/api/v1/encounters/{encounter_id}/approvals', status_code=201)
async def post_approval(request: Request, encounter_id: str):
    session = session_of(request)
    auth.require(session, 'approve')
    body = await request.json()
    with transaction() as conn:
        encounter = get_encounter(conn, session['organisation_id'], encounter_id, lock=True)
        if encounter is None:
            raise not_found('visit')
        existing = approval_of(conn, encounter_id, body.get('expected_version'))
        if existing and existing['content_hash'] == body.get('expected_content_hash'):
            # A replayed approval returns the recorded result; it never approves twice.
            return envelope(conn, session, encounter, report_row(conn, encounter_id, existing['version'], 'approved'))
        if encounter['state'] != 'in_review':
            raise ApiError(409, 'not_in_review', 'Only a draft in review can be approved.')
        row = report_row(conn, encounter_id, encounter['current_version'], 'draft')
        check_expected(row, body)
        now = datetime.now(timezone.utc)
        try:
            approved = approve(parse_report(row), f"{session['display_name']} ({session['user_id']})", now)
        except ApprovalBlocked as blocked:
            raise ApiError(409, 'approval_blocked', 'Resolve every blocking issue before approving.',
                           issue_codes=[i.code for i in blocked.issues]) from None
        except HashMismatch:
            raise ApiError(409, 'version_conflict', 'This draft changed. Reload and review the latest version.') from None
        approval_id = 'apr-' + uuid.uuid4().hex[:12]
        conn.execute('insert into app.approvals (id, encounter_id, version, content_hash, approver_id, approved_at) '
                     'values (%s, %s, %s, %s, %s, %s)',
                     (approval_id, encounter_id, approved.version, approved.content_hash, session['user_id'], now))
        conn.execute('insert into app.report_versions (encounter_id, version, status, report, content_hash, created_by) '
                     "values (%s, %s, 'approved', %s, %s, %s)",
                     (encounter_id, approved.version, Jsonb(approved.model_dump(mode='json')), approved.content_hash,
                      session['user_id']))
        for kind in ('report_pdf', 'fhir_bundles'):
            conn.execute('insert into app.artifacts (id, encounter_id, approval_id, version, kind) values (%s, %s, %s, %s, %s)',
                         ('art-' + uuid.uuid4().hex[:12], encounter_id, approval_id, approved.version, kind))
        conn.execute("update app.encounters set state = 'approved', approved_version = %s where id = %s",
                     (approved.version, encounter_id))
        patient = get_patient(conn, session['organisation_id'], encounter['patient_id'])
        clinic_job = state['followup'].clinic_reports.queue_approval(conn,encounter,approved,patient,approval_id)
        try:
            initialize_followup(conn, encounter, approved, patient,
                                clinic_copy_contact=clinic_job['recipient'] if clinic_job else None,
                                registered_delivery=bool(clinic_job and clinic_job.get('delivery_mode')=='patient'))
        except GateRefused:
            pass  # Approval succeeds even when consent/language/synthetic eligibility prevents follow-up.
        audit(conn, session['user_id'], session['organisation_id'], 'draft.approved', 'encounter', encounter_id,
              {'version': approved.version, 'content_hash': approved.content_hash})
        return envelope(conn, session, encounter, report_row(conn, encounter_id, approved.version, 'approved'))


@app.get('/api/v1/encounters/{encounter_id}/artifacts')
def list_artifacts(request: Request, encounter_id: str):
    session = session_of(request)
    with transaction() as conn:
        if get_encounter(conn, session['organisation_id'], encounter_id) is None:
            raise not_found('visit')
        rows = artifacts_of(conn, encounter_id)
    return {'items': [{**a, 'created_at': a['created_at'].isoformat(), 'updated_at': a['updated_at'].isoformat()}
                      for a in rows]}


@app.get('/api/v1/encounters/{encounter_id}/clinic-reports')
def clinic_report_status(request: Request, encounter_id: str):
    session=session_of(request)
    with transaction() as conn:
        encounter=get_encounter(conn,session['organisation_id'],encounter_id)
        if encounter is None:
            raise not_found('visit')
        return {'items':clinic_deliveries(conn,encounter_id,encounter['approved_version'])}


@app.post('/api/v1/encounters/{encounter_id}/clinic-reports/retry')
def retry_clinic_reports(request: Request, encounter_id: str):
    session=session_of(request);auth.require(session,'resolve')
    with transaction() as conn:
        encounter=get_encounter(conn,session['organisation_id'],encounter_id,lock=True)
        if encounter is None:
            raise not_found('visit')
        conn.execute("update app.clinic_report_jobs set state='pending',attempts=0,error=null,provider_id=null,not_before=now(),"
                     "updated_at=now() where encounter_id=%s and version=%s and state='failed'",
                     (encounter_id,encounter['approved_version']))
        audit(conn,session['user_id'],session['organisation_id'],'clinic_report.retry','encounter',encounter_id)
        return {'items':clinic_deliveries(conn,encounter_id,encounter['approved_version'])}


@app.get('/api/v1/artifacts/{artifact_id}/download')
def download(request: Request, artifact_id: str):
    session = session_of(request)
    with transaction() as conn:
        row = one(conn, '''select a.*, p.mrn from app.artifacts a join app.encounters e on e.id = a.encounter_id
                           join app.patients p on p.id = e.patient_id where a.id = %s and e.organisation_id = %s''',
                  (artifact_id, session['organisation_id']))
    if row is None:
        raise not_found('file')
    if row['state'] != 'ready':
        raise ApiError(409, 'artifact_not_ready', 'This file is not ready yet.', retryable=True)
    path = state['settings'].artifacts_dir / row['encounter_id'] / f"v{row['version']}" / row['file_name']
    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != row['sha256']:
        with transaction() as conn:
            saved=one(conn,'select sha256,data from app.artifact_files where artifact_id=%s',(artifact_id,))
        if saved and saved['sha256']==row['sha256'] and sha256(bytes(saved['data'])).hexdigest()==row['sha256']:
            return Response(bytes(saved['data']),media_type='application/pdf' if row['kind']=='report_pdf' else 'application/json',
                            headers={'Cache-Control':'private, no-store','Content-Disposition':f'attachment; filename="{row["file_name"]}"'})
        if row['kind']=='report_pdf':
            with transaction() as conn:
                archived=one(conn,'select sha256,data from app.report_files where encounter_id=%s and version=%s',
                             (row['encounter_id'],row['version']))
            if archived and sha256(bytes(archived['data'])).hexdigest()==archived['sha256']==row['sha256']:
                return Response(bytes(archived['data']),media_type='application/pdf',headers={
                    'Cache-Control':'private, no-store','Content-Disposition':f'attachment; filename="approved-v{row["version"]}.pdf"'})
        raise ApiError(410, 'artifact_changed', 'This file is missing or no longer matches its record.')
    return FileResponse(path, filename=f"{row['mrn']}-v{row['version']}-{row['file_name']}")


@app.get('/api/v1/encounters/{encounter_id}/preview.pdf')
def preview_pdf(request: Request, encounter_id: str, version: int | None = None):
    """A draft PDF, watermarked as not approved, rendered on request and not stored."""
    session = session_of(request)
    with transaction() as conn:
        encounter = get_encounter(conn, session['organisation_id'], encounter_id)
        if encounter is None:
            raise not_found('visit')
        row = report_row(conn, encounter_id, version)
    if row is None:
        raise ApiError(404, 'no_report', 'This visit has no report yet.')
    report = parse_report(row)
    with tempfile.TemporaryDirectory() as folder:
        pdf = html_to_pdf(render_html(report, build_patient_box(report, TEMPLATES)), Path(folder) / 'preview.pdf')
        data = pdf.read_bytes()
    return Response(data, media_type='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="preview-v{report.version}.pdf"'})


# ---------- Product catalogue (spec 2026-11-03, part C) ----------

@app.get('/api/v1/encounters/{encounter_id}/shortlist')
def encounter_shortlist(request: Request, encounter_id: str):
    """The medicines usually prescribed for this visit's conditions (runbook D-122), made once and kept."""
    session = session_of(request)
    auth.require(session, 'resolve')
    with transaction() as conn:
        encounter = get_encounter(conn, session['organisation_id'], encounter_id)
        if encounter is None:
            raise not_found('visit')
        row = one(conn, 'select conditions, items from app.medicine_shortlists where encounter_id = %s', (encounter_id,))
        if row is None and encounter['current_version']:
            draft = parse_report(report_row(conn, encounter_id, encounter['current_version'], None))
            patient = one(conn, 'select birth_year from app.patients where id = %s', (encounter['patient_id'],))
            shortlist = shortlist_for(conn, state['worker'].llm(), draft.checked, session['organisation_id'], REFERENCE.products,
                                      is_adult(patient, encounter['visit_date']))
            save_shortlist(conn, encounter_id, *shortlist)
            row = {'conditions': shortlist[0], 'items': shortlist[1]}
    return {'conditions': row['conditions'] if row else [], 'items': row['items'] if row else []}


@app.get('/api/v1/catalog/search')
def catalog_search(request: Request, q: str = ''):
    """Products by name across the formulary, the Indian list and the clinic's own, sound-alikes included."""
    session = session_of(request)
    auth.require(session, 'resolve')
    if len(q.strip()) < 2:
        return {'items': []}
    with transaction() as conn:
        found = {}
        for pool in (shared_index(conn, REFERENCE.products), clinic_index(conn, session['organisation_id'])):
            for c in pool.candidates(q[:80], limit=10):
                if c.entry.id not in found or c.score > found[c.entry.id].score:
                    found[c.entry.id] = c
        stock = load_stock(conn, session['organisation_id'])
    # Widely sold and listed products first among equally close names: typing "pan" finds PAN 40 before Panday.
    # In-stock products at the hospital pharmacy lead only among names that sound almost equally close.
    ranked = sorted(found.values(), key=lambda c: (c.strength_match is not False, c.score + standing(c.entry)
                                                   + (stock.bonus(c.entry) if stock else 0)),
                    reverse=True)[:10]
    # Formulary aliases are indexed under the alias ("Pan" for Pan-D); show the product's own label.
    label = lambda c: product_label(REFERENCE.products[c.entry.id]) if c.entry.id in REFERENCE.products else c.entry.name
    rules = load_rules(REPO_ROOT)

    def defaults(c):
        food, once_daily, _ = standard_for([p.ingredient for p in parse_composition(c.entry.composition)], rules)
        return {'food': food, 'once_daily': once_daily, 'form': entry_form(c.entry) or 'tablet'}
    return {'items': [{'id': c.entry.id, 'label': label(c), 'composition': c.entry.composition,
                       'tier': c.entry.tier, 'strength_match': c.strength_match, **defaults(c),
                       'stock': stock.badge(c.entry.id, c.entry.name, c.entry.composition) if stock else None}
                      for c in ranked]}


@app.post('/api/v1/catalog/products', status_code=201)
async def add_product(request: Request):
    """A product the lists lack, added for this clinic and pending review. It can be chosen at once."""
    session = session_of(request)
    auth.require(session, 'resolve')
    body = await request.json()
    name = ' '.join(str(body.get('name') or '').split())
    form = str(body.get('form') or 'other')
    composition = ' '.join(str(body.get('composition') or '').split())
    if not 2 <= len(name) <= 80:
        raise ApiError(422, 'invalid_product', 'Give the brand name as on the pack.')
    if form not in set(FORMS.values()) | {'other'}:
        raise ApiError(422, 'invalid_product', 'Choose the form from the list.')
    if not composition or len(composition) > 300 or not all(c.ingredient for c in parse_composition(composition)):
        raise ApiError(422, 'invalid_product', 'Give the composition, for example "Pantoprazole (40mg)".')
    product_id = 'cp-' + uuid.uuid4().hex[:12]
    with transaction() as conn:
        conn.execute('insert into app.clinic_products (id, organisation_id, name, form, composition, created_by) '
                     'values (%s, %s, %s, %s, %s, %s)',
                     (product_id, session['organisation_id'], name, form, composition, session['user_id']))
        audit(conn, session['user_id'], session['organisation_id'], 'catalog.product_added', 'clinic_product', product_id,
              {'name': name, 'composition': composition})
    return {'id': product_id, 'label': name, 'composition': composition, 'tier': 'clinic', 'status': 'pending_review'}


# ---------- Hospital pharmacy stock (runbook D-126 to D-128) ----------

@app.get('/api/v1/pharmacy/stock')
def pharmacy_stock(request: Request):
    session = session_of(request)
    auth.require(session, 'pharmacy')  # doctors and the hospital admin; not reception
    with transaction() as conn:
        return pharmacy_summary(conn, session['organisation_id'])


@app.post('/api/v1/pharmacy/stock', status_code=201)
async def upload_pharmacy_stock(request: Request):
    """A full stock snapshot as CSV text: {filename, csv}. It replaces the hospital's previous snapshot."""
    session = session_of(request)
    auth.require(session, 'pharmacy')  # doctors and the hospital admin; not reception
    body = await request.json()
    text = body.get('csv')
    if not isinstance(text, str) or not text.strip():
        raise ApiError(422, 'invalid_stock', 'Choose a stock file exported as CSV.')
    filename = ' '.join(str(body.get('filename') or 'stock.csv').split())[:120]
    with transaction() as conn:
        try:
            result = import_stock(conn, session['organisation_id'], session['user_id'], filename, text, REFERENCE.products)
        except StockFileError as error:
            raise ApiError(422, 'invalid_stock', str(error)) from None
        audit(conn, session['user_id'], session['organisation_id'], 'pharmacy.stock_imported', 'organisation',
              session['organisation_id'], {'filename': filename, 'rows': result['rows'], 'matched': result['matched']})
    return result


# ---------- Reference knowledge ----------

@app.post('/api/v1/knowledge/search')
async def knowledge_search(request: Request):
    session = session_of(request)
    auth.require(session, 'knowledge')
    body = await request.json()
    question = body.get('question') if isinstance(body.get('question'), str) else ''
    if not question.strip():
        raise ApiError(422, 'empty_question', 'Type a question first.')
    ingredients, scope = None, None
    with transaction() as conn:
        if body.get('encounter_id') and body.get('medication_id'):
            encounter = get_encounter(conn, session['organisation_id'], str(body['encounter_id']))
            row = report_row(conn, encounter['id']) if encounter else None
            if row is None:
                raise not_found('visit')
            report = parse_report(row)
            rx = next((m for m in report.checked.medications if m.id == body['medication_id']), None)
            if rx is None:
                raise not_found('medicine')
            products = {**REFERENCE.products, **report.products_used}
            ids = [rx.product_id] if rx.product_id else rx.candidate_ids
            ingredients = sorted({k for pid in ids if pid in products for k in knowledge.ingredient_keys(products[pid])})
            scope = {'medication_id': rx.id, 'ingredients': ingredients}
        results = knowledge.search(conn, question, ingredients)
    return {'results': results, 'scope': scope,
            'note': "Reference passages from US drug labels (openFDA), India's NLEM 2022 and the Jan Aushadhi list. "
                    'Not part of the record and not checked against this patient. Scores rank passages; '
                    'they are not medical confidence.'}


# ---------- Web app ----------

install_followup_routes(app, state, session_of, ApiError)
install_workspace(app,state,session_of,ApiError)
install_audio_uploads(app,session_of,ApiError,store_audio,AUDIO_TYPES,LANGUAGE_CODES)

app.mount('/static', StaticFiles(directory=WEB / 'static'), name='static')


@app.get('/')
def index(request:Request):
    """The sign-in page until there is a session, then the doctor app (Rakshit's 5 Nov design, runbook D-129).
    The sign-in page holds no product data, so it is the same in private and development modes."""
    try:
        session_of(request)
    except auth.NotSignedIn:
        return FileResponse(WEB / 'login.html', headers={'Cache-Control': 'no-store'})
    return FileResponse(WEB / 'index.html', headers={'Cache-Control': 'no-cache'})


@app.get('/v1')
def index_v1():
    """The previous interface (app_v2 of 4 Nov), kept as a fallback beside the new design."""
    return FileResponse(WEB / 'static' / 'app_v2' / 'index.html', headers={'Cache-Control': 'no-cache'})


AUTH_ASSETS = ('base.css', 'login.css', 'login.js')


@app.get('/auth-assets/{name}')
def auth_asset(name:str):
    # Public before sign-in; base.css is also the doctor app's foundation. Versioned URLs bust the cache.
    if name not in AUTH_ASSETS:
        raise not_found('file')
    return FileResponse(WEB / 'auth-assets' / name,headers={'Cache-Control':'no-cache'})
