"""A recording sent in pieces during the visit and transcribed as it arrives (runbook D-131).

The browser's recorder hands over a piece every second and the app sends what it has every ten seconds.
Joined, the pieces are the browser's own file, and a file cut short decodes to exactly the samples the
whole file has, so the server decodes what has arrived and sends Prisma each finished segment (at most
29 seconds, cut where it is quietest) while the visit goes on. When the doctor stops, only the last
segment is left, and the file becomes the visit's source without a second upload.

Anything that goes wrong here costs only the head start: the run then transcribes the stored recording
the usual way.
"""
import logging
import threading
from collections import OrderedDict
from uuid import uuid4

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from psycopg.types.json import Jsonb

from . import auth
from .config import read_env
from .db import audit, one, transaction
from .repo import get_encounter, get_patient
from ..speech.prisma import RATE, _post, decode_audio, segments, transcribe_segment, transcript_meta

log = logging.getLogger(__name__)
PART = 3 * 1024 * 1024
MAX_BYTES = 40 * 1024 * 1024
MAX_SECONDS = 20 * 60 + 30
# The last second of a file cut short can still change when more arrives, so a segment ends before it.
SETTLED = RATE
SHORTEST = int(0.3 * RATE)


class Files:
    """The file so far for recordings this process is taking, so a piece does not read back every piece
    before it. Another process, or a restart, reads the pieces from the database instead."""
    def __init__(self, keep=32):
        self.keep, self.lock, self.items = keep, threading.Lock(), OrderedDict()

    def get(self, lid, parts):
        with self.lock:
            held = self.items.get(lid)
            return held[1] if held and held[0] == parts else None

    def put(self, lid, parts, data):
        with self.lock:
            self.items[lid] = (parts, data)
            self.items.move_to_end(lid)
            while len(self.items) > self.keep:
                self.items.popitem(last=False)

    def drop(self, lid):
        with self.lock:
            self.items.pop(lid, None)


FILES = Files()


def file_so_far(conn, row):
    data = FILES.get(row['id'], row['next_part'])
    if data is None:
        data = b''.join(bytes(r['data']) for r in conn.execute(
            'select data from app.live_recording_parts where live_id = %s order by part', (row['id'],)).fetchall())
    return data


def poster():
    return _post(read_env()['GNANI_API_KEY'])


def advance(data, language, done, texts, final, post):
    """Transcribes every segment after `done` that is complete (all of them once `final`).
    Returns (done, texts, segments sent, samples so far, error); an error stops at the segment it hit."""
    try:
        samples = decode_audio(data)
    except Exception as error:
        return done, texts, 0, None, f'{type(error).__name__}: {error}'
    settled = samples if final else samples[:max(done, len(samples) - SETTLED)]
    tail = settled[done:]
    parts = segments(tail) if len(tail) else []
    ready = parts if final else parts[:-1]
    base, sent = done, 0
    try:
        for start, end in ready:
            if end - start >= SHORTEST:
                text = transcribe_segment(tail[start:end], language, texts, post)
                if text:
                    texts = [*texts, text]
                sent += 1
            done = base + end
    except Exception as error:
        return done, texts, sent, len(samples), f'{type(error).__name__}: {error}'[:300]
    return done, texts, sent, len(samples), None


def live_transcript(conn, source):
    """The transcript made during the visit for this source, if it covers the whole recording."""
    live = one(conn, 'select * from app.live_recordings where source_id = %s and finished and error is null',
               (source['id'],))
    if not live or not live['texts'] or live['done_samples'] != live['total_samples']:
        return None, None
    conn.execute('delete from app.live_recordings where id = %s', (live['id'],))
    return ' '.join(live['texts']), transcript_meta(source['language'], live['segments'], live['total_samples'] / RATE,
                                                    live=True)


def status(row):
    return {'id': row['id'], 'parts': row['next_part'], 'heard_s': round(row['total_samples'] / RATE, 1),
            'transcribed_s': round(row['done_samples'] / RATE, 1), 'segments': row['segments'],
            'finished': row['finished'], 'behind': bool(row['error'])}


def install(app, session_of, ApiError, store_audio, audio_types, languages):
    def owned(conn, session, lid):
        row = one(conn, 'select l.* from app.live_recordings l join app.encounters e on e.id = l.encounter_id '
                        'where l.id = %s and l.user_id = %s and e.organisation_id = %s and l.expires_at > now() '
                        'for update of l', (lid, session['user_id'], session['organisation_id']))
        if not row:
            raise ApiError(404, 'not_found', 'Recording not found or expired.')
        return row

    @app.post('/api/v1/encounters/{eid}/live-recordings', status_code=201)
    async def begin(request: Request, eid: str):
        s = session_of(request)
        auth.require(s, 'capture')
        body = await request.json()
        media = str(body.get('media_type') or '').split(';')[0].strip().lower()
        language = body.get('language')
        if media not in audio_types or language not in languages:
            raise ApiError(422, 'invalid_audio', 'Choose a supported recording format and language.')
        if body.get('recording_consent') is not True:
            raise ApiError(422, 'consent_required', 'Confirm consent to the recording.')
        with transaction() as conn:
            encounter = get_encounter(conn, s['organisation_id'], eid, lock=True)
            if not encounter:
                raise ApiError(404, 'not_found', 'Visit not found.')
            if encounter['state'] not in ('open', 'failed'):
                raise ApiError(409, 'source_locked', 'This visit has already been processed.')
            if 'recording' not in get_patient(conn, s['organisation_id'], encounter['patient_id'])['consents']:
                raise ApiError(422, 'no_recording_consent', "This patient's record has no consent to recording.")
            # A new recording replaces one started earlier for this visit and never used.
            conn.execute('delete from app.live_recordings where expires_at < now() or '
                         '(encounter_id = %s and source_id is null)', (eid,))
            lid = 'live-' + uuid4().hex
            conn.execute('insert into app.live_recordings (id, encounter_id, user_id, media_type, language) '
                         'values (%s, %s, %s, %s, %s)', (lid, eid, s['user_id'], media, language))
            audit(conn, s['user_id'], s['organisation_id'], 'recording.live_started', 'encounter', eid,
                  {'live_recording_id': lid, 'language': language})
        return {'id': lid, 'part_bytes': PART}

    def take(s, lid, part, data, final):
        with transaction() as conn:
            row = owned(conn, s, lid)
            if part < row['next_part']:
                return status(row)  # a repeat of a piece already taken
            if row['finished'] or row['source_id']:
                raise ApiError(409, 'recording_finished', 'This recording has already been finished.')
            if part != row['next_part']:
                raise ApiError(409, 'part_out_of_order', f"Send piece {row['next_part']} next.")
            joined = file_so_far(conn, row) + data
            if len(joined) > MAX_BYTES:
                raise ApiError(413, 'audio_too_large', 'Recordings are limited to 40 MB.')
            done, texts, sent, total, error = advance(joined, row['language'], row['done_samples'], row['texts'], final,
                                                      poster())
            if total is not None and total > MAX_SECONDS * RATE:
                raise ApiError(422, 'audio_too_long', 'Recordings are limited to 20 minutes.')
            if error:
                log.warning('live transcription of %s is behind: %s', lid, error)
            conn.execute('insert into app.live_recording_parts (live_id, part, data) values (%s, %s, %s)', (lid, part, data))
            conn.execute('update app.live_recordings set bytes = %s, next_part = %s, texts = %s, done_samples = %s, '
                         'total_samples = %s, segments = segments + %s, finished = %s, error = %s where id = %s',
                         (len(joined), part + 1, Jsonb(texts), done, total if total is not None else row['total_samples'],
                          sent, final, error, lid))
            taken = one(conn, 'select * from app.live_recordings where id = %s', (lid,))
        FILES.put(lid, part + 1, joined)
        return status(taken)

    @app.put('/api/v1/live-recordings/{lid}/parts/{part}')
    async def part(request: Request, lid: str, part: int, final: bool = False):
        s = session_of(request)
        auth.require(s, 'capture')
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > PART:
                raise ApiError(413, 'part_too_large', 'A recording piece is over 3 MB.')
        if not data and not final:
            raise ApiError(422, 'empty_part', 'The recording piece is empty.')
        return await run_in_threadpool(take, s, lid, part, bytes(data), final)

    @app.post('/api/v1/live-recordings/{lid}/complete')
    async def complete(request: Request, lid: str):
        """The finished recording becomes the visit's source, checked like any upload."""
        s = session_of(request)
        auth.require(s, 'capture')
        with transaction() as conn:
            row = owned(conn, s, lid)
            if row['source_id']:
                source = one(conn, 'select id, encounter_id, version, kind, language, duration_s from app.sources '
                                   'where id = %s', (row['source_id'],))
                return {**source, 'duration_s': float(source['duration_s'])}
            if not row['finished']:
                raise ApiError(409, 'recording_unfinished', 'The recording has not been finished yet.')
            result = await store_audio(s, row['encounter_id'], row['media_type'], row['language'], file_so_far(conn, row))
            # The file now lives with the source; only the transcript waits here for the run.
            conn.execute('update app.live_recordings set source_id = %s where id = %s', (result['id'], lid))
            conn.execute('delete from app.live_recording_parts where live_id = %s', (lid,))
        FILES.drop(lid)
        return {**result, 'live': status({**row, 'finished': True})}
