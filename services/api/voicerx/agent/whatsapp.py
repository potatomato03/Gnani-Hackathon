"""Real WhatsApp through Meta's Cloud API, for private testing on the team's own phones (runbook D-113).

The submitted demo stays the simulated chat (D-105), because the challenge bans real phone numbers. Here:
- a phone number lives only in memory; a conversation stores a keyed hash of it, never the number;
- only numbers listed in WHATSAPP_TEST_NUMBERS are served, and every visit is synthetic;
- every message sent is one the conversation core already passed through the gate (agent/gate.py);
- free-form messages go out only inside WhatsApp's 24-hour customer-service window.

Facts from developers.facebook.com (read 3 Nov 2026): Graph API v26.0. POST /{phone_number_id}/messages sends;
reply buttons are at most 3, each title at most 20 characters, body at most 1024. A voice message is Ogg Opus
sent with "voice": true. Media upload is POST /{phone_number_id}/media (multipart); GET /{media_id} gives a URL
valid for 5 minutes, fetched with the same bearer token. Webhooks are signed with X-Hub-Signature-256
(HMAC-SHA256 of the body with the app secret).
"""
import hashlib
import hmac
import json
import logging
import re
import urllib.error
import urllib.request
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..ingest.gnani import CLINIC_VOICE, ENV_FILE, TTS_MODEL, SpeechError, read_env, ssl_context, tts_language

GRAPH_BASE = 'https://graph.facebook.com'
GRAPH_VERSION = 'v26.0'
WINDOW = timedelta(hours=24)
BODY_LIMIT, TITLE_LIMIT, MAX_BUTTONS = 1024, 20, 3
# Interactive list (4 to 10 choices, e.g. the quick menu, D-117): body 4096, button label 20, row title 24.
LIST_BODY_LIMIT, ROW_TITLE_LIMIT, MAX_ROWS, LIST_BUTTON = 4096, 24, 10, 'Menu'
JOIN = re.compile(r'^\s*join\s+([A-Za-z0-9_\-]+)\s*$', re.IGNORECASE)
REQUIRED = ('WHATSAPP_TOKEN', 'WHATSAPP_PHONE_NUMBER_ID', 'WHATSAPP_APP_SECRET', 'WHATSAPP_VERIFY_TOKEN',
            'WHATSAPP_TEST_NUMBERS')
HELP = ('VoiceRx follow-up test bot. Synthetic data only, not for real patients.\n'
        'To start, send JOIN and a visit code, for example: {example}\n'
        'Visit codes: {codes}\n\n'
        'VoiceRx फ़ॉलो-अप टेस्ट बॉट (सिर्फ़ सिंथेटिक डेटा)। शुरू करने के लिए JOIN और विज़िट कोड भेजें।')
log = logging.getLogger('voicerx.whatsapp')


def digits(text):
    return re.sub(r'\D', '', text or '')


@dataclass(frozen=True, repr=False)
class WhatsAppConfig:
    token: str
    phone_number_id: str
    app_secret: str
    verify_token: str
    test_numbers: frozenset
    graph_base: str = GRAPH_BASE
    graph_version: str = GRAPH_VERSION

    def __repr__(self):
        return (f'WhatsAppConfig(phone_number_id={self.phone_number_id!r}, token=<hidden>, app_secret=<hidden>, '
                f'test_numbers=<{len(self.test_numbers)} hidden>)')

    @classmethod
    def from_env(cls, env_path: Path = ENV_FILE):
        """The config when every setting is present (env vars or the ignored .env), else None: WhatsApp is off."""
        values = {name: read_env(name, env_path) for name in REQUIRED}
        if not all(values.values()):
            return None
        numbers = frozenset(filter(None, (digits(n) for n in values['WHATSAPP_TEST_NUMBERS'].split(','))))
        return cls(token=values['WHATSAPP_TOKEN'], phone_number_id=values['WHATSAPP_PHONE_NUMBER_ID'],
                   app_secret=values['WHATSAPP_APP_SECRET'], verify_token=values['WHATSAPP_VERIFY_TOKEN'],
                   test_numbers=numbers, graph_base=read_env('WHATSAPP_GRAPH_BASE', env_path) or GRAPH_BASE,
                   graph_version=read_env('WHATSAPP_GRAPH_VERSION', env_path) or GRAPH_VERSION)


class WhatsAppError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f'WhatsApp returned HTTP {status}: {message}')


class DeliveryHeld(Exception):
    """Nothing was sent; the messages stay queued and go out after the patient's next message."""


def scrub(text, secrets=()):
    """Remove the token and anything that looks like a phone number from text that may be shown or logged."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, '<hidden>')
    return re.sub(r'\+?\d[\d\s-]{7,}\d', '<number>', text)


def http_request(method, url, headers, body):
    request = urllib.request.Request(url, data=body, method=method, headers={**headers, 'User-Agent': 'voicerx'})
    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read()


def _error_message(data):
    try:
        error = json.loads(data.decode('utf-8')).get('error') or {}
    except (ValueError, UnicodeDecodeError, AttributeError):
        return 'no readable error message'
    return ' '.join(str(part) for part in (error.get('code'), error.get('message')) if part) or 'error'


class GraphClient:
    def __init__(self, config: WhatsAppConfig, transport=None):
        self.config, self.transport = config, transport or http_request

    def __repr__(self):
        return 'GraphClient(token=<hidden>)'

    def _url(self, path):
        return f'{self.config.graph_base}/{self.config.graph_version}/{path}'

    def _call(self, method, url, body=None, content_type=None):
        headers = {'Authorization': f'Bearer {self.config.token}'}
        if content_type:
            headers['Content-Type'] = content_type
        status, _, data = self.transport(method, url, headers, body)
        if status != 200:
            raise WhatsAppError(status, scrub(_error_message(data), [self.config.token, self.config.app_secret]))
        return data

    def _post(self, path, payload):
        body = json.dumps({'messaging_product': 'whatsapp', **payload}, ensure_ascii=False).encode('utf-8')
        return json.loads(self._call('POST', self._url(path), body, 'application/json').decode('utf-8'))

    def _message(self, to, payload):
        return self._post(f'{self.config.phone_number_id}/messages', {'recipient_type': 'individual', 'to': to,
                                                                       **payload})

    def send_text(self, to, text):
        return self._message(to, {'type': 'text', 'text': {'body': text, 'preview_url': False}})

    def send_buttons(self, to, text, buttons):
        return self._message(to, {'type': 'interactive', 'interactive': {
            'type': 'button', 'body': {'text': text},
            'action': {'buttons': [{'type': 'reply', 'reply': {'id': i, 'title': label}} for i, label in buttons]}}})

    def send_list(self, to, text, button_label, rows):
        return self._message(to, {'type': 'interactive', 'interactive': {
            'type': 'list', 'body': {'text': text},
            'action': {'button': button_label,
                       'sections': [{'title': button_label, 'rows': [{'id': i, 'title': t} for i, t in rows]}]}}})

    def send_audio(self, to, media_id, voice=True):
        return self._message(to, {'type': 'audio', 'audio': {'id': media_id, 'voice': voice}})

    def upload_audio(self, data, mime='audio/ogg'):
        boundary = uuid.uuid4().hex
        body = b''.join([
            f'--{boundary}\r\nContent-Disposition: form-data; name="messaging_product"\r\n\r\nwhatsapp\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\n{mime}\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="reply.ogg"\r\n'
            f'Content-Type: {mime}\r\n\r\n'.encode() + data + b'\r\n',
            f'--{boundary}--\r\n'.encode()])
        reply = self._call('POST', self._url(f'{self.config.phone_number_id}/media'), body,
                           'multipart/form-data; boundary=' + boundary)
        return json.loads(reply.decode('utf-8'))['id']

    def download_media(self, media_id):
        """A patient's voice note: held in memory by the caller, never written to disk."""
        info = json.loads(self._call(
            'GET', self._url(f'{media_id}?phone_number_id={self.config.phone_number_id}')).decode('utf-8'))
        if not str(info.get('url', '')).startswith('https://'):
            raise WhatsAppError(502, 'media URL missing or not https')
        return self._call('GET', info['url'])

    def enable_calling(self):
        """Calling is off by default, also on test numbers. Body as in Meta's call-settings docs (3 Nov 2026)."""
        body = json.dumps({'calling': {'status': 'ENABLED', 'call_icon_visibility': 'DEFAULT'}}).encode('utf-8')
        return json.loads(self._call('POST', self._url(f'{self.config.phone_number_id}/settings'), body,
                                     'application/json').decode('utf-8'))

    def call_action(self, call_id, action, sdp=None):
        payload = {'call_id': call_id, 'action': action}
        if sdp is not None:
            payload['session'] = {'sdp_type': 'answer', 'sdp': sdp}
        return self._post(f'{self.config.phone_number_id}/calls', payload)


def verify_signature(body: bytes, header: str | None, app_secret: str) -> bool:
    if not header or not header.startswith('sha256='):
        return False
    expected = hmac.new(app_secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len('sha256='):])


@dataclass
class Inbound:
    sender: str
    message_id: str
    kind: str                 # text, button, audio, or the WhatsApp type we don't handle
    text: str | None = None
    button: str | None = None
    media_id: str | None = None


@dataclass
class CallEvent:
    sender: str
    call_id: str
    event: str                # connect, terminate, ...
    sdp: str | None = None


def _user(value, item, keys):
    """The patient's number: the contact's wa_id, else the first of keys that isn't the business number."""
    business = digits(value.get('metadata', {}).get('display_phone_number'))
    contacts = value.get('contacts') or []
    if contacts and contacts[0].get('wa_id'):
        return digits(contacts[0]['wa_id'])
    for key in keys:
        number = digits(item.get(key))
        if number and number != business:
            return number
    return ''


def parse_webhook(payload):
    """(messages, call events) from one webhook delivery. Delivery statuses are ignored."""
    messages, calls = [], []
    for entry in payload.get('entry') or []:
        for change in entry.get('changes') or []:
            value = change.get('value') or {}
            for item in value.get('messages') or []:
                kind = item.get('type')
                inbound = Inbound(sender=_user(value, item, ['from']), message_id=str(item.get('id', '')),
                                  kind=kind)
                if kind == 'text':
                    inbound.text = (item.get('text') or {}).get('body', '')
                elif kind == 'interactive' and (item.get('interactive') or {}).get('type') == 'button_reply':
                    inbound.kind, inbound.button = 'button', item['interactive']['button_reply'].get('id')
                elif kind == 'button':   # a quick-reply button on a template message
                    inbound.kind, inbound.text = 'text', (item.get('button') or {}).get('text', '')
                elif kind == 'audio':
                    inbound.media_id = (item.get('audio') or {}).get('id')
                messages.append(inbound)
            for item in value.get('calls') or []:
                session = item.get('session') or {}
                calls.append(CallEvent(sender=_user(value, item, ['from', 'to']), call_id=str(item.get('id', '')),
                                       event=item.get('event', ''), sdp=session.get('sdp')))
    return messages, calls


class WhatsAppChannel:
    name = 'whatsapp'

    def __init__(self, config: WhatsAppConfig, graph: GraphClient | None = None, now=None):
        self.config = config
        self.graph = graph or GraphClient(config)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._numbers: dict[str, str] = {}     # contact hash -> phone number, in memory only
        self._seen: OrderedDict[str, None] = OrderedDict()

    def __repr__(self):
        return 'WhatsAppChannel(<hidden>)'

    @classmethod
    def from_env(cls):
        config = WhatsAppConfig.from_env()
        return cls(config) if config else None

    def allowed(self, number):
        return number in self.config.test_numbers

    def contact(self, number):
        key = hmac.new(self.config.app_secret.encode(), number.encode(), hashlib.sha256).hexdigest()[:16]
        self._numbers[key] = number
        return key

    def first_time(self, message_id):
        """Meta retries a webhook it thinks failed; handle each message id once."""
        if message_id in self._seen:
            return False
        self._seen[message_id] = None
        while len(self._seen) > 2000:
            self._seen.popitem(last=False)
        return True

    def send_help(self, number, codes):
        codes = list(codes) or ['fam-010-a']
        self.graph.send_text(number, HELP.format(example=f'JOIN {codes[0]}', codes=', '.join(codes)))

    def deliver(self, conv, speech=None, audio_dir: Path | None = None) -> int:
        """Send every clinic message not yet handed to WhatsApp. Raises DeliveryHeld when it may not send now."""
        if conv.plan.channel != 'whatsapp' or not conv.contact:
            return 0
        pending = list(enumerate(conv.messages))[conv.delivered:]
        if not any(m.sender == 'clinic' for _, m in pending):
            conv.delivered = len(conv.messages)
            return 0
        number = self._numbers.get(conv.contact)
        if number is None:
            raise DeliveryHeld("waiting for the phone: the server restarted, so queued messages go out after the "
                               "patient's next WhatsApp message")
        if conv.last_inbound_at is None or self.now() - conv.last_inbound_at > WINDOW:
            raise DeliveryHeld("outside WhatsApp's 24-hour window: queued messages go out after the patient's "
                               "next WhatsApp message")
        sent = 0
        for index, message in pending:
            if message.sender == 'clinic':
                self._send(number, message)
                sent += 1
                if conv.last_inbound_voice and speech is not None and audio_dir is not None:
                    self._send_voice(number, conv, message, speech, audio_dir)
            conv.delivered = index + 1
        return sent

    def _send(self, number, message):
        buttons = [(b.id, b.label) for b in message.buttons]
        fits = (len(message.text) <= BODY_LIMIT and len(buttons) <= MAX_BUTTONS
                and all(len(label) <= TITLE_LIMIT for _, label in buttons))
        listed = (len(message.text) <= LIST_BODY_LIMIT and len(buttons) <= MAX_ROWS
                  and all(len(label) <= ROW_TITLE_LIMIT for _, label in buttons))
        if buttons and fits:
            self.graph.send_buttons(number, message.text, buttons)
        elif buttons and listed:
            self.graph.send_list(number, message.text, LIST_BUTTON, buttons)
        elif buttons:   # too long for buttons or a list: the labels are typed answers the router already reads
            self.graph.send_text(number, message.text + '\n\n' + '\n'.join(f'• {label}' for _, label in buttons))
        else:
            self.graph.send_text(number, message.text)

    def _send_voice(self, number, conv, message, speech, audio_dir):
        """The same gated text, spoken by Timbre as a WhatsApp voice note (Ogg Opus), cached by content."""
        from .voice import cache_name
        language = tts_language(conv.language)
        path = Path(audio_dir) / f'{cache_name(TTS_MODEL, CLINIC_VOICE, language, "ogg", message.text)}.ogg'
        try:
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(speech.synthesize(message.text, language, CLINIC_VOICE, container='ogg',
                                                   sample_rate=24000))
            data = path.read_bytes()
            if not data.startswith(b'OggS'):
                raise WhatsAppError(0, 'Timbre did not return Ogg audio')
            self.graph.send_audio(number, self.graph.upload_audio(data, 'audio/ogg'), voice=True)
        except (SpeechError, WhatsAppError) as error:
            log.warning('voice reply not sent (the text was): %s', scrub(str(error), [self.config.token]))


def main(argv=None):
    """python -m voicerx.agent.whatsapp enable-calling: switch on calls for the number in .env."""
    import argparse
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('command', choices=['enable-calling'])
    parser.parse_args(argv)
    config = WhatsAppConfig.from_env()
    if config is None:
        raise SystemExit('WhatsApp settings are missing from .env (see docs/whatsapp-testing.md)')
    GraphClient(config).enable_calling()
    print('Calling is on for the WhatsApp number. Subscribe the app to the "calls" webhook field too.')


if __name__ == '__main__':
    main()
