"""HTTP API for the simulated WhatsApp follow-up demo. Synthetic data only; no model or speech calls.

Run from the repo root:
    PYTHONPATH=services/api .venv/bin/uvicorn voicerx.app:app --port 8000
"""
import os
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent import conversation as chat
from .agent.demo import DEMO_VISITS, build_visit
from .agent.gate import GateRefused
from .contracts.followup import TASK_ORDER, Conversation
from .pipeline.assemble import table_medicines
from .pipeline.run import REPO_ROOT

DEFAULT_STATE = REPO_ROOT / 'runs/followup-demo'


class Inbound(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    button: str | None = Field(default=None, min_length=1, max_length=40)

    @model_validator(mode='after')
    def exactly_one(self):
        if (self.text is None) == (self.button is None):
            raise ValueError('send either text or a button')
        return self


def create_app(state_dir: Path = DEFAULT_STATE) -> FastAPI:
    state_dir = Path(state_dir)
    lock = threading.RLock()
    visits, conversations = {}, {}

    def visit(case_id):
        if case_id not in DEMO_VISITS:
            raise HTTPException(404, 'unknown demo visit')
        if case_id not in visits:
            visits[case_id] = build_visit(case_id, state_dir / 'visits')
        return visits[case_id]

    def conversation(conversation_id) -> Conversation:
        if conversation_id not in conversations:
            path = state_dir / 'conversations' / f'{conversation_id}.json'
            if not conversation_id.isalnum() or not path.exists():
                raise HTTPException(404, 'unknown conversation')
            stored = Conversation.model_validate_json(path.read_text(encoding='utf-8'))
            conversations[conversation_id] = chat.attach(stored, visit(stored.case_id))
        return conversations[conversation_id]

    def view(conv, **extra):
        chat.save(conv, state_dir / 'conversations')
        return {**conv.model_dump(mode='json'), **extra}

    app = FastAPI(title='VoiceRx follow-up demo (synthetic data)')
    origins = os.environ.get('VOICERX_WEB_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET', 'POST'],
                       allow_headers=['Content-Type'])

    @app.get('/health')
    def health():
        return {'ok': True, 'synthetic': True}

    @app.get('/demo/visits')
    def demo_visits():
        with lock:
            out = []
            for case_id in DEMO_VISITS:
                approved = visit(case_id).approved
                products = approved.products_used
                out.append({'case_id': case_id, 'synthetic': True, 'patient_name': approved.header.patient_name,
                            'doctor_name': approved.header.doctor_name, 'clinic_name': approved.header.clinic_name,
                            'language': approved.language_pref, 'visit_date': approved.header.visit_date.isoformat(),
                            'medicines': [products[m.product_id].brand for m in table_medicines(approved.checked)
                                          if m.product_id in products]})
            return out

    @app.post('/demo/visits/{case_id}/start')
    def start(case_id: str):
        with lock:
            conv = chat.start(visit(case_id), uuid4().hex[:12])
            conversations[conv.id] = conv
            return view(conv)

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

    @app.get('/clinic/tasks')
    def clinic_tasks():
        with lock:
            stored = state_dir / 'conversations'
            for path in stored.glob('*.json') if stored.exists() else []:
                conversation(path.stem)  # include conversations saved before a restart
            tasks = [{**t.model_dump(mode='json'), 'conversation_id': c.id, 'patient_name': c.patient_name,
                      'case_id': c.case_id}
                     for c in conversations.values() for t in c.tasks if t.status == 'open']
            tasks.sort(key=lambda t: t['created_at'], reverse=True)
            tasks.sort(key=lambda t: TASK_ORDER.index(t['kind']))
            return tasks

    return app


app = create_app()
