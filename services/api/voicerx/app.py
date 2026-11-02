"""HTTP API for the follow-up agent: the simulated WhatsApp chat, voice notes and approved visits.

Synthetic data only. Gnani speech is used only when GNANI_API_KEY is set, and only on demand: a clinic
message is voiced when someone taps Listen (then cached), a patient voice note is transcribed when sent.

Run from the repo root:
    PYTHONPATH=services/api .venv/bin/uvicorn voicerx.app:app --port 8000
"""
import os
import re
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent import conversation as chat
from .agent import visits as visit_store
from .agent.demo import DEMO_VISITS, build_visit
from .agent.gate import CONSENT, GateRefused
from .agent.voice import MAX_BYTES, VoiceRefused, synthetic_voice_note, transcribe_voice_note, voice_message
from .contracts.followup import TASK_ORDER, Conversation
from .ingest.gnani import SpeechError, speech_from_env
from .pipeline.assemble import table_medicines

AUDIO_NAME = re.compile(r'[0-9a-f]{32}\.mp3')
AUTO = object()


class Inbound(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    button: str | None = Field(default=None, min_length=1, max_length=40)

    @model_validator(mode='after')
    def exactly_one(self):
        if (self.text is None) == (self.button is None):
            raise ValueError('send either text or a button')
        return self


class SyntheticVoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=300)


def default_speech():
    if os.environ.get('VOICERX_FAKE_SPEECH') == '1':   # offline browser check only; never with a real key
        from .ingest.fake_speech import FakeSpeech
        return FakeSpeech()
    return speech_from_env()


def create_app(state_dir: Path | None = None, runs_root: Path | None = None, speech=AUTO) -> FastAPI:
    # By default the app reads runs/ and keeps its state in runs/followup-demo/. Given only a state dir (tests),
    # it reads nothing outside it.
    runs_root = Path(runs_root or (visit_store.RUNS if state_dir is None else state_dir))
    state_dir = Path(state_dir or visit_store.STATE)
    audio_dir = state_dir / 'audio'
    speech = default_speech() if speech is AUTO else speech
    lock = threading.RLock()
    conversations: dict[str, Conversation] = {}
    known: dict[str, visit_store.Visit] = {}
    demo_built = {}

    def all_visits():
        """Demo fixtures (built once per process) plus every approved report under runs/."""
        for case_id in DEMO_VISITS:
            if case_id not in demo_built:
                demo_built[case_id] = build_visit(case_id, state_dir / 'visits')
        found = {}
        for root in (runs_root, state_dir / 'visits'):
            for v in visit_store.find_approved_visits(root)[0]:
                found.setdefault(str(Path(v.path).resolve()), v)
        known.clear()
        for v in found.values():
            known[v.visit_id] = v
        return list(found.values())

    def visit_for(conv: Conversation):
        if conv.visit_id not in known:
            all_visits()
        if conv.visit_id in known and known[conv.visit_id].approved.content_hash == conv.report_hash:
            return known[conv.visit_id]
        raise HTTPException(410, 'the approved report this conversation ran from is gone or changed')

    def conversation(conversation_id) -> Conversation:
        if conversation_id not in conversations:
            path = state_dir / 'conversations' / f'{conversation_id}.json'
            if not conversation_id.isalnum() or not path.exists():
                raise HTTPException(404, 'unknown conversation')
            stored = Conversation.model_validate_json(path.read_text(encoding='utf-8'))
            conversations[conversation_id] = chat.attach(stored, visit_for(stored))
        return conversations[conversation_id]

    def view(conv, **extra):
        chat.save(conv, state_dir / 'conversations')
        return {**conv.model_dump(mode='json'), **extra}

    def need_speech():
        if speech is None:
            raise HTTPException(503, 'voice is off: GNANI_API_KEY is not set')
        return speech

    def start(visit, restart):
        try:
            conv = visit_store.start_followup(visit, state_dir, restart=restart)
        except GateRefused as refusal:
            raise HTTPException(409, f'not started: {refusal}') from None
        conversations[conv.id] = conv
        return view(conv)

    def describe(v):
        approved, products = v.approved, v.approved.products_used
        running = [c for c in visit_store.stored_conversations(state_dir) if c.visit_id == v.visit_id]
        return {'visit_id': v.visit_id, 'case_id': v.case_id, 'source': v.source, 'synthetic': True,
                'patient_name': approved.header.patient_name, 'doctor_name': approved.header.doctor_name,
                'clinic_name': approved.header.clinic_name, 'language': approved.language_pref,
                'visit_date': approved.header.visit_date.isoformat(), 'approved_by': approved.approved_by,
                'review_date': v.review_date.isoformat() if v.review_date else None,
                'consent': CONSENT in v.consents,
                'medicines': [products[m.product_id].brand for m in table_medicines(approved.checked)
                              if m.product_id in products],
                'conversation_id': running[-1].id if running else None}

    app = FastAPI(title='VoiceRx follow-up (synthetic data)')
    origins = os.environ.get('VOICERX_WEB_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET', 'POST'],
                       allow_headers=['Content-Type'])

    @app.get('/health')
    def health():
        mode = 'off' if speech is None else getattr(speech, 'name', 'gnani')
        return {'ok': True, 'synthetic': True, 'speech': mode}

    @app.get('/visits')
    def list_visits():
        with lock:
            order = {case_id: i for i, case_id in enumerate(DEMO_VISITS)}
            out = [describe(v) for v in all_visits()]
            return sorted(out, key=lambda v: (v['source'] != 'demo', order.get(v['case_id'], 99), v['visit_date']))

    @app.post('/visits/{visit_id}/start')
    def start_visit(visit_id: str, restart: bool = False):
        with lock:
            all_visits()
            if visit_id not in known:
                raise HTTPException(404, 'unknown approved visit')
            return start(known[visit_id], restart)

    # Older demo routes, kept for the first version of the web page.
    @app.get('/demo/visits')
    def demo_visits():
        return [v for v in list_visits() if v['source'] == 'demo']

    @app.post('/demo/visits/{case_id}/start')
    def start_demo(case_id: str):
        with lock:
            match = [v for v in all_visits() if v.source == 'demo' and v.case_id == case_id]
            if not match:
                raise HTTPException(404, 'unknown demo visit')
            return start(match[0], restart=True)

    @app.post('/demo/reset')
    def reset():
        with lock:
            conversations.clear()
            for path in (state_dir / 'conversations').glob('*.json'):
                path.unlink()
            return {'reset': True}

    @app.get('/conversations/{conversation_id}')
    def get_conversation(conversation_id: str):
        with lock:
            return conversation(conversation_id).model_dump(mode='json')

    @app.post('/conversations/{conversation_id}/messages')
    def post_message(conversation_id: str, inbound: Inbound):
        with lock:
            conv = conversation(conversation_id)
            try:
                chat.receive(conv, text=inbound.text, button=inbound.button)
            except GateRefused as refusal:
                raise HTTPException(409, f'not sent: {refusal}') from None
            return view(conv)

    @app.post('/conversations/{conversation_id}/advance')
    def advance(conversation_id: str):
        with lock:
            conv = conversation(conversation_id)
            try:
                advanced = chat.advance(conv)
            except GateRefused as refusal:
                raise HTTPException(409, f'not sent: {refusal}') from None
            return view(conv, advanced=advanced)

    @app.post('/conversations/{conversation_id}/messages/{message_id}/voice')
    def voice(conversation_id: str, message_id: str):
        with lock:
            conv = conversation(conversation_id)
            try:
                name, cached = voice_message(conv, message_id, need_speech(), audio_dir)
            except VoiceRefused as refusal:
                raise HTTPException(422, str(refusal)) from None
            except SpeechError as error:
                raise HTTPException(502, str(error)) from None
            view(conv)
            return {'audio_url': f'/audio/{name}.mp3', 'cached': cached}

    @app.get('/audio/{name}')
    def audio(name: str):
        path = audio_dir / name
        if not AUDIO_NAME.fullmatch(name) or not path.exists():
            raise HTTPException(404, 'no such audio')
        data = path.read_bytes()
        kind = 'audio/wav' if data[:4] == b'RIFF' else 'audio/mpeg'
        return Response(data, media_type=kind, headers={'Cache-Control': 'private, max-age=86400'})

    @app.post('/conversations/{conversation_id}/voice')
    async def voice_note(conversation_id: str, request: Request):
        if int(request.headers.get('content-length') or 0) > MAX_BYTES:
            raise HTTPException(413, 'voice note is too large')
        clip = await request.body()   # held in memory only; never written to disk
        with lock:
            conv = conversation(conversation_id)
            try:
                transcribe_voice_note(conv, clip, need_speech())
            except VoiceRefused as refusal:
                raise HTTPException(422, str(refusal)) from None
            except SpeechError as error:
                raise HTTPException(502, str(error)) from None
            except GateRefused as refusal:
                raise HTTPException(409, f'not sent: {refusal}') from None
            return view(conv)

    @app.post('/conversations/{conversation_id}/voice/synthetic')
    def voice_synthetic(conversation_id: str, body: SyntheticVoice):
        with lock:
            conv = conversation(conversation_id)
            try:
                synthetic_voice_note(conv, body.text, need_speech(), audio_dir)
            except VoiceRefused as refusal:
                raise HTTPException(422, str(refusal)) from None
            except SpeechError as error:
                raise HTTPException(502, str(error)) from None
            except GateRefused as refusal:
                raise HTTPException(409, f'not sent: {refusal}') from None
            return view(conv)

    @app.get('/clinic/tasks')
    def clinic_tasks():
        with lock:
            stored = state_dir / 'conversations'
            for path in stored.glob('*.json') if stored.exists() else []:
                try:
                    conversation(path.stem)  # include conversations saved before a restart
                except HTTPException:
                    continue
            tasks = [{**t.model_dump(mode='json'), 'conversation_id': c.id, 'patient_name': c.patient_name,
                      'case_id': c.case_id}
                     for c in conversations.values() for t in c.tasks if t.status == 'open']
            tasks.sort(key=lambda t: t['created_at'], reverse=True)
            tasks.sort(key=lambda t: TASK_ORDER.index(t['kind']))
            return tasks

    return app


app = create_app()
