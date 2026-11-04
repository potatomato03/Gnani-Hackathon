"""Per-patient memory (runbook D-118): what each patient told the clinic, and the reports they sent.

Kept in Supabase (`patient_memory`, `patient_documents`, migration in supabase/migrations/) with a local JSONL
fallback under the state dir. A patient is a keyed hash (WhatsApp) or "sim-<patient_id>" (demo), never a phone
number. No raw document, audio or number is stored.
"""
import hashlib
import hmac
import json
import logging
import re
import time
from pathlib import Path

import psycopg

from ..contracts.documents import PatientDocument
from ..contracts.followup import Conversation, FollowUpRecord, MemoryItem
from ..ingest.gnani import ENV_FILE, read_env

log = logging.getLogger('voicerx.memory')
PLAIN_KEY = re.compile(r'[A-Za-z0-9_-]{1,80}')
# Which doctor tasks become memory, and as what. Urgent tasks are covered by their warning-sign items.
TASK_MEMORY = {'question': 'question', 'callback': 'request', 'consult_request': 'request',
               'side_effect': 'problem', 'worse': 'problem', 'stopped_medicine': 'problem'}


def patient_key_for_number(number: str, key: str) -> str:
    return hmac.new(key.encode('utf-8'), number.encode('utf-8'), hashlib.sha256).hexdigest()[:16]


def patient_key_for_simulated(conv: Conversation) -> str:
    return 'sim-' + conv.patient_id


def items_from_record(conv: Conversation, record: FollowUpRecord) -> list[MemoryItem]:
    patient_key = conv.patient_key or patient_key_for_simulated(conv)
    source = record.transcript_source or 'typed'
    found = [('answer', f'{a.question}: {a.value}', a.quote) for a in record.answers]
    found += [('warning_sign', flag, record.raw_text or None) for flag in record.red_flags]
    found += [(TASK_MEMORY[t.kind], t.note, record.raw_text or None) for t in conv.tasks
              if t.record_id == record.id and t.kind in TASK_MEMORY]
    return [MemoryItem(id=f'{record.id}-{n}', patient_key=patient_key, visit_ref=conv.case_id, kind=kind, text=text,
                       quote=quote, source=source, source_ref=record.id, at=record.received_at)
            for n, (kind, text, quote) in enumerate(found, 1)]


class LocalMemoryStore:
    """One JSONL file per patient. For tests, offline runs, and when Supabase is unreachable."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _file(self, kind, patient_key):
        if not PLAIN_KEY.fullmatch(patient_key):
            raise ValueError('patient key must be a plain name')
        return self.directory / kind / f'{patient_key}.jsonl'

    def _read(self, path, model):
        if not path.exists():
            return []
        return [model.model_validate_json(line) for line in path.read_text(encoding='utf-8').splitlines() if line]

    def _append(self, path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as out:
            out.writelines(row.model_dump_json() + '\n' for row in rows)

    def add(self, items):
        for item in items:
            path = self._file('items', item.patient_key)
            if item.id not in {i.id for i in self._read(path, MemoryItem)}:
                self._append(path, [item])

    def recent(self, patient_key, limit=20):
        return sorted(self._read(self._file('items', patient_key), MemoryItem), key=lambda i: i.at)[-limit:]

    def add_document(self, doc):
        path = self._file('documents', doc.patient_key)
        if any(d.sha256 == doc.sha256 for d in self._read(path, PatientDocument)):
            return False
        self._append(path, [doc])
        return True

    def documents(self, patient_key):
        return self._read(self._file('documents', patient_key), PatientDocument)


def _no_nul(value):
    """Postgres text and jsonb refuse NUL characters, which pypdf can return (live check, 4 Nov)."""
    return value.replace('\x00', '').replace('\\u0000', '') if isinstance(value, str) else value   # raw, or JSON-escaped


class SupabaseMemoryStore:
    """Postgres over SUPABASE_DB_URL. Row-level security is on with no policy: only the backend reads (D-103)."""

    COLUMNS = ('id', 'patient_key', 'visit_ref', 'kind', 'text', 'quote', 'source', 'source_ref', 'at')

    def __init__(self, db_url: str):
        self.db_url = db_url

    def __repr__(self):
        return 'SupabaseMemoryStore(<hidden>)'

    def _connect(self):
        return psycopg.connect(self.db_url, connect_timeout=10)

    def add(self, items):
        if not items:
            return
        with self._connect() as db:
            db.cursor().executemany(
                f'insert into patient_memory ({", ".join(self.COLUMNS)}, synthetic) '
                f'values ({", ".join(["%s"] * len(self.COLUMNS))}, true) on conflict (id) do nothing',
                [tuple(_no_nul(getattr(i, c)) for c in self.COLUMNS) for i in items])

    def recent(self, patient_key, limit=20):
        with self._connect() as db:
            rows = db.execute(f'select {", ".join(self.COLUMNS)} from patient_memory where patient_key = %s '
                              'order by at desc limit %s', (patient_key, limit)).fetchall()
        return [MemoryItem(**dict(zip(self.COLUMNS, row))) for row in reversed(rows)]

    def add_document(self, doc):
        with self._connect() as db:
            cursor = db.execute(
                'insert into patient_documents (id, patient_key, visit_ref, mime, sha256, pages, method, reading, '
                'received_at, synthetic) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, true) '
                'on conflict (patient_key, sha256) do nothing',
                (doc.id, doc.patient_key, doc.visit_ref, doc.mime, doc.sha256, doc.pages, doc.method,
                 _no_nul(doc.reading.model_dump_json()), doc.received_at))
            return cursor.rowcount == 1

    def documents(self, patient_key):
        with self._connect() as db:
            rows = db.execute('select id, patient_key, visit_ref, mime, sha256, pages, method, reading, received_at '
                              'from patient_documents where patient_key = %s order by received_at',
                              (patient_key,)).fetchall()
        names = ('id', 'patient_key', 'visit_ref', 'mime', 'sha256', 'pages', 'method', 'reading', 'received_at')
        return [PatientDocument(**dict(zip(names, row))) for row in rows]


class SafeMemory:
    """Supabase first; on any database or network error, the local store, so the chat never stops. Reads include
    what was written locally, so nothing that fell back goes missing.
    ponytail: writes made during an outage stay local and aren't copied up later; add a sync if outages matter."""

    def __init__(self, primary, fallback, cooldown=300, clock=time.monotonic):
        """cooldown: seconds Supabase rests after a failure, so a paused project doesn't cost a 10 s connect
        timeout on every message."""
        self.primary, self.fallback, self.cooldown, self.clock = primary, fallback, cooldown, clock
        self.resting_until = 0.0

    def _try(self, name, *args):
        if self.clock() < self.resting_until:
            return getattr(self.fallback, name)(*args)
        try:
            return getattr(self.primary, name)(*args)
        except (psycopg.Error, OSError) as error:
            log.warning('patient memory: Supabase unavailable (%s), using the local store', type(error).__name__)
            self.resting_until = self.clock() + self.cooldown
            return getattr(self.fallback, name)(*args)

    def add(self, items):
        return self._try('add', items)

    def recent(self, patient_key, limit=20):
        found = {i.id: i for i in self._try('recent', patient_key, limit)}
        for i in self.fallback.recent(patient_key, limit):
            found.setdefault(i.id, i)
        return sorted(found.values(), key=lambda i: i.at)[-limit:]

    def add_document(self, doc):
        return self._try('add_document', doc)

    def documents(self, patient_key):
        found = {d.id: d for d in self._try('documents', patient_key)}
        for d in self.fallback.documents(patient_key):
            found.setdefault(d.id, d)
        return sorted(found.values(), key=lambda d: d.received_at)


def memory_from_env(state_dir: Path, env_path: Path = ENV_FILE):
    local = LocalMemoryStore(Path(state_dir) / 'memory')
    db_url = read_env('SUPABASE_DB_URL', env_path)
    if db_url and read_env('VOICERX_MEMORY', env_path) != 'local':
        return SafeMemory(SupabaseMemoryStore(db_url), local)
    return local
