"""Gnani speech: Prisma v3.0 speech-to-text and Timbre v3.0 text-to-speech over REST.

Facts from docs.gnani.ai (read 3 Nov 2026):
- Prisma REST: POST https://api.vachana.ai/stt/v3, multipart (audio_file, model, language_code, format),
  clips up to 30 s, format read from the file extension.
- Timbre REST: POST https://api.vachana.ai/api/v1/tts/inference, JSON, raw audio back.
- Both take the key in X-API-Key-ID. Some accounts allow one active request at a time (429 RATE_LIMITED).

The key is sent only in its header. It never appears in a URL, a log, an error or a file (CLAUDE.md rule 2).
Every call spends Gnani credits of unknown cost (Q-03), so callers keep calls on demand and cache output.
"""
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

STT_URL = 'https://api.vachana.ai/stt/v3'
TTS_URL = 'https://api.vachana.ai/api/v1/tts/inference'
STT_MODEL = 'prisma-v3.0'
TTS_MODEL = 'timbre-v3.0'
CLINIC_VOICE = 'Chetana'      # Timbre v3.0: "gentle, empathetic voice for healthcare"
PATIENT_VOICE = 'Shubham'     # used only for synthetic patient voice notes
MAX_SECONDS = 30
RETRIES = 3
_ONE_AT_A_TIME = threading.Lock()
AUDIO_TYPES = {'wav': 'audio/wav', 'ogg': 'audio/ogg', 'mp3': 'audio/mpeg'}


class SpeechError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f'Gnani returned HTTP {status}: {message}')


@dataclass
class Transcript:
    text: str
    detected_language: str | None
    truncated: bool


def stt_languages(language_pref):
    """Prisma hints: the patient's language first, then the other one they are likely to mix in."""
    return {'hi-IN': 'hi-IN,en-IN', 'en-IN': 'en-IN,hi-IN'}.get(language_pref, language_pref)


def tts_language(language_pref):
    # Hindi follow-up text mixes Devanagari with Latin brand names; Gnani recommends auto for mixed script.
    return 'auto' if language_pref == 'hi-IN' else language_pref


def ssl_context():
    context = ssl.create_default_context()
    bundle = os.environ.get('SSL_CERT_FILE') or ('/root/.ccr/ca-bundle.crt' if Path('/root/.ccr/ca-bundle.crt').exists() else None)
    if bundle:
        context.load_verify_locations(bundle)
    return context


def http_transport(url, headers, body):
    request = urllib.request.Request(url, data=body, method='POST', headers={**headers, 'User-Agent': 'voicerx'})
    try:
        with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read()


class GnaniSpeech:
    def __init__(self, key, transport=None, sleep=time.sleep):
        if not key:
            raise ValueError('a Gnani API key is required')
        self.key, self.transport, self.sleep = key, transport or http_transport, sleep

    def __repr__(self):
        return 'GnaniSpeech(key=<hidden>)'

    def transcribe(self, audio_bytes, language_code, filename='voice-note.wav') -> Transcript:
        """Prisma reads the format from the file name: wav, mp3, ogg, flac, aac or m4a."""
        boundary = uuid.uuid4().hex
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode('utf-8')
                 for name, value in (('model', STT_MODEL), ('language_code', language_code), ('format', 'codemix'))]
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="audio_file"; filename="{filename}"\r\n'
                     f'Content-Type: {AUDIO_TYPES[filename.rsplit(".", 1)[-1]]}\r\n\r\n'.encode('utf-8')
                     + audio_bytes + b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode('utf-8'))
        body = self._call(STT_URL, 'multipart/form-data; boundary=' + boundary, b''.join(parts))
        reply = json.loads(body.decode('utf-8'))
        return Transcript(text=(reply.get('transcript') or '').strip(),
                          detected_language=reply.get('detected_language_code'),
                          truncated=bool(reply.get('truncated')))

    def synthesize(self, text, language, voice, container='mp3', sample_rate=24000) -> bytes:
        config = {'sample_rate': sample_rate, 'num_channels': 1, 'sample_width': 2, 'container': container}
        if container == 'mp3':
            config['bitrate'] = '64k'
        else:
            config['encoding'] = 'linear_pcm'
        body = json.dumps({'text': text, 'model': TTS_MODEL, 'voice': voice, 'language': language, 'speed': 1.0,
                           'audio_config': config}, ensure_ascii=False).encode('utf-8')
        return self._call(TTS_URL, 'application/json', body)

    def _call(self, url, content_type, body):
        headers = {'X-API-Key-ID': self.key, 'Content-Type': content_type}
        for attempt in range(RETRIES + 1):
            with _ONE_AT_A_TIME:
                status, _, data = self.transport(url, headers, body)
            if status == 200:
                return data
            if status == 429 and attempt < RETRIES:
                self.sleep(1.5 * (attempt + 1))
                continue
            raise SpeechError(status, _message(data).replace(self.key, '<hidden>'))
        raise SpeechError(429, 'still rate limited after retries')


def _message(data):
    try:
        reply = json.loads(data.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return 'no readable error message'
    detail = reply.get('detail')
    if isinstance(detail, dict):
        return detail.get('message') or detail.get('error_code') or 'error'
    if isinstance(reply.get('error'), dict):
        return reply['error'].get('message') or reply['error'].get('type') or 'error'
    return reply.get('message') or str(detail or 'error')


ENV_FILE = Path(__file__).resolve().parents[4] / '.env'


def read_env(name, env_path: Path = ENV_FILE):
    """A setting from the environment, else from the repo's ignored .env file, else None."""
    value = os.environ.get(name, '').strip()
    if value:
        return value
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if line.startswith(name + '='):
                return line.split('=', 1)[1].strip() or None
    return None


def read_key(env_path: Path = ENV_FILE):
    return read_env('GNANI_API_KEY', env_path)


def speech_from_env(env_path: Path = ENV_FILE):
    """A client when a key is configured, else None (voice is off)."""
    key = read_key(env_path)
    return GnaniSpeech(key) if key else None
