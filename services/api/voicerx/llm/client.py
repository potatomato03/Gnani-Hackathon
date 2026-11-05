"""Validated provider calls with atomic caching and bounded retries."""
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import time
import urllib.request
import urllib.error
from threading import Lock
from uuid import uuid4
from pydantic import BaseModel, ValidationError

_LOCAL_LOCK = Lock()
# Gemini models tried after GEMINI_MODEL for chat messages. On 4 Nov these answered while 3.8 and 3.7 were busy.
QUICK_FALLBACK = 'gemini-3.5-flash,gemini-3.5-flash-lite'
_CACHE_LOCK = Lock()


@dataclass
class CallMeta:
    provider: str
    model: str
    prompt_version: str
    cache_key: str
    cached: bool
    key_index: int
    attempts: int


class QuotaExhausted(Exception):
    pass


class ModelOutputInvalid(Exception):
    pass


def json_schema_for(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    definitions = schema.get('$defs', {})
    def expand(node):
        if isinstance(node, list):
            return [expand(x) for x in node]
        if not isinstance(node, dict):
            return node
        if '$ref' in node:
            return expand(definitions[node['$ref'].split('/')[-1]])
        result = {k: expand(v) for k, v in node.items() if k not in ('$defs', 'title', 'default')}
        if result.get('type') == 'object':
            result['additionalProperties'] = False
            result['required'] = list(result.get('properties', {}))
        return result
    return expand(schema)


def transport(url, headers, body, timeout=300):
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                     headers=headers, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read().decode('utf-8')
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode('utf-8', 'replace')
    except TimeoutError:
        return 504, {}, 'timed out'  # A slow server is retried, not written off for the run.
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            return 504, {}, 'timed out'
        return 0, {}, 'server unavailable'
    except OSError:
        return 0, {}, 'server unavailable'


def retry_delay(headers, attempt):
    value = next((v for k, v in headers.items() if k.casefold() == 'retry-after'), None)
    if value:
        try:
            return max(0, float(value))
        except ValueError:
            try:
                return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                pass
    return 20 * attempt


class ModelClient:
    def __init__(self, adapter, keys, cache_dir: Path, transport=None, sleep=time.sleep, max_transient=6,
                 timeout=300, cooldown=None, clock=time.monotonic, repair=True, rotate_on_limit=True,
                 wait_when_limited=True):
        """max_transient: tries per key on 429/5xx. A chat message uses 1 and a short timeout, so a busy
        provider falls back to the rules in seconds instead of minutes (runbook D-115). cooldown: seconds a
        key that was busy or unreachable rests before it is tried again; None means for the rest of the run.
        A daily quota always ends the key for the run. rotate_on_limit: a per-minute 429 rests that key until its
        retry-after and moves to the next key at once. wait_when_limited: when every key is resting, wait for the
        first to free up (the last provider in line) or raise QuotaExhausted so an overflow provider answers."""
        self.adapter, self.keys, self.cache_dir = adapter, keys, Path(cache_dir)
        self.max_transient, self.timeout, self.cooldown, self.clock = max_transient, timeout, cooldown, clock
        self.allow_repair = repair      # chat: no second "fix your JSON" request; the next model is tried instead
        self.transport = transport or partial(globals()['transport'], timeout=timeout)
        self.sleep = sleep
        self.exhausted = set()
        self.resting = {}           # key index -> clock time it may be tried again
        self.rotate_on_limit, self.wait_when_limited = rotate_on_limit, wait_when_limited
        self.limited = {}           # key index -> clock time its per-minute limit resets

    def _rest(self, index):
        if self.cooldown is None:
            self.exhausted.add(index)
        else:
            self.resting[index] = self.clock() + self.cooldown

    def generate(self, system, user, schema, prompt_version, attachments=()):
        """attachments: (mime type, bytes) pairs, e.g. a report photo (D-119); only adapters that declare
        supports_attachments take them."""
        if attachments and not getattr(self.adapter, 'supports_attachments', False):
            raise QuotaExhausted(f'{self.adapter.name}: cannot read attachments')
        if self.adapter.name == 'ollama':
            with _LOCAL_LOCK:
                return self._generate(system, user, schema, prompt_version, attachments)
        return self._generate(system, user, schema, prompt_version, attachments)

    def _generate(self, system, user, schema, prompt_version, attachments=()):
        attached = [[mime, sha256(data).hexdigest()] for mime, data in attachments]
        fingerprint = json.dumps([self.adapter.name, self.adapter.model, prompt_version, system, user, *attached],
                                 ensure_ascii=False)
        cache_key = sha256(fingerprint.encode('utf-8')).hexdigest()
        path = self.cache_dir / (cache_key + '.json')
        if path.exists():
            try:
                with _CACHE_LOCK:
                    cached = json.loads(path.read_text(encoding='utf-8'))
                parsed = schema.model_validate_json(cached['reply'])
                return parsed, replace(CallMeta(**cached['meta']), cached=True)
            except (ValueError, KeyError, TypeError):
                pass  # Corrupt or obsolete cache entries never bypass validation.
        attempts = 0
        repair = False
        request_user = user
        waits = 0
        while True:
            result = self._try_keys(system, request_user, user, schema, prompt_version, attachments, cache_key, path,
                                    attempts, repair)
            if result[0] == 'done':
                return result[1], result[2]
            _, attempts, repair, request_user = result
            # Every key is at its per-minute limit. The last provider in line waits for the first key to free up;
            # one with an overflow provider behind it hands over at once (runbook D-130).
            limited = [t for i, t in self.limited.items() if i not in self.exhausted]
            if not limited or not self.wait_when_limited or waits >= self.max_transient:
                raise QuotaExhausted(f'{self.adapter.name}: no available key or server')
            waits += 1
            self.sleep(max(0.0, min(limited) - self.clock()))

    def _try_keys(self, system, request_user, user, schema, prompt_version, attachments, cache_key, path, attempts,
                  repair):
        for index, key in enumerate(self.keys):
            if index in self.exhausted or self.resting.get(index, 0) > self.clock() \
                    or self.limited.get(index, 0) > self.clock():
                continue
            transient = 0
            while transient < self.max_transient:
                extra = {'attachments': attachments} if attachments else {}
                url, headers, body = self.adapter.build(system, request_user, json_schema_for(schema), key, **extra)
                status, response_headers, text = self.transport(url, headers, body)
                attempts += 1
                if self.adapter.is_quota_exhausted(status, response_headers, text):
                    self.exhausted.add(index)
                    break
                if status == 0:
                    self._rest(index)
                    break
                if status == 429 and self.rotate_on_limit:
                    # A per-minute limit: this key rests until the provider says, and the next key is tried now
                    # instead of sleeping on this one (measured 21-96 s of sleeping per visit on 5 Nov).
                    self.limited[index] = self.clock() + retry_delay(response_headers, 1)
                    break
                if status == 429 or status >= 500:
                    transient += 1
                    if transient < self.max_transient:
                        self.sleep(retry_delay(response_headers, transient))
                    else:
                        self._rest(index)
                    continue
                rejected = status != 200 and getattr(self.adapter, 'is_invalid_output', lambda s, t: False)(status, text)
                if status != 200 and not rejected:
                    raise ModelOutputInvalid(f'{self.adapter.name} HTTP {status}')
                try:
                    if rejected:
                        raise ValueError('provider rejected the generated JSON against the schema')
                    reply = self.adapter.reply_text(json.loads(text))
                    if any(len(k) > 8 and k in reply for k in self.keys):
                        raise ValueError('credential appeared in response')
                    parsed = schema.model_validate_json(reply)
                except (ValueError, KeyError, TypeError, ValidationError) as error:
                    if repair or not self.allow_repair:
                        raise ModelOutputInvalid(f'{self.adapter.name}: invalid response after repair') from None
                    repair = True
                    # Do not include raw provider data or credentials in errors or logs.
                    detail = str(error)
                    for secret in self.keys:
                        if len(secret) > 8:
                            detail = detail.replace(secret, '<redacted>')
                    request_user = user + '\nReturn a complete corrected object matching the schema. Validation: ' + detail[:3000]
                    continue
                meta = CallMeta(self.adapter.name, self.adapter.model, prompt_version, cache_key, False, index, attempts)
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.stem + '.' + uuid4().hex + '.tmp')
                try:
                    temporary.write_text(json.dumps({'reply': reply, 'meta': asdict(meta)}, ensure_ascii=False), encoding='utf-8')
                    with _CACHE_LOCK:
                        temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
                return 'done', parsed, meta
        return 'busy', attempts, repair, request_user


class FallbackClient:
    def __init__(self, clients, budget=None, clock=time.monotonic):
        """budget: seconds after which no further provider is started (chat and documents, D-115), and an
        invalid reply then moves on to the next provider instead of failing. None: the pipeline's behaviour."""
        self.clients, self.budget, self.clock = clients, budget, clock

    def generate(self, system, user, schema, prompt_version, attachments=()):
        started = self.clock()
        for client in self.clients:
            if attachments and not getattr(client.adapter, 'supports_attachments', False):
                continue
            if self.budget is not None and self.clock() - started >= self.budget:
                break
            try:
                return client.generate(system, user, schema, prompt_version, attachments)
            except QuotaExhausted:
                continue
            except ModelOutputInvalid:
                if self.budget is None:
                    raise
        raise QuotaExhausted('all configured providers unavailable')


def build_client(env_path: Path, cache_dir: Path, only=None, quick=False, timeout=None, budget=None):
    """quick=True is for chat messages: one try per key, no waiting, and the fallback models when one is busy
    (gemini-3.8-flash returned 503 or ran past 60 s on 4 Nov). timeout is per request (default 10 s) and budget
    the whole call (default 25 s); the budget must leave room for a fallback after one slow model."""
    from .gemini import DEFAULT_MODEL, GeminiAdapter
    from .ollama import OllamaAdapter
    from .openai_compat import OpenAICompatAdapter, mistral
    settings = {}
    for line in (env_path.read_text(encoding='utf-8-sig').splitlines() if env_path.exists() else []):
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            settings[key.strip()] = value.strip().strip('\"\'')
    import os
    settings.update(os.environ)
    options = ({'max_transient': 1, 'timeout': timeout or 10, 'cooldown': 60, 'sleep': lambda seconds: None,
                'repair': False, 'rotate_on_limit': False} if quick else {})
    clients = []
    keys = [settings[k] for k in ('GEMINI_API_KEY', 'GEMINI_API_KEY_2') if settings.get(k)]
    if keys and only in (None, 'gemini'):
        fallback = settings.get('GEMINI_FALLBACK_MODEL') or (QUICK_FALLBACK if quick else '')
        models = list(dict.fromkeys([settings.get('GEMINI_MODEL') or DEFAULT_MODEL,
                                     *filter(None, (m.strip() for m in fallback.split(',')))]))
        clients.extend(ModelClient(GeminiAdapter(model), keys, cache_dir, **options) for model in models)
    groq_keys = [settings[k] for k in ('GROQ_API_KEY', 'GROQ_API_KEY_2') if settings.get(k)]
    mistral_keys = [settings[k] for k in ('MISTRAL_API_KEY',) if settings.get(k)]
    # LLM_OVERFLOW=mistral: when every Groq key is at its per-minute limit, Mistral answers at once instead of
    # the pipeline sleeping (runbook D-130). Off unless set, and only after Mistral passed the typed-case eval.
    overflow = settings.get('LLM_OVERFLOW') == 'mistral' and mistral_keys and only in (None, 'groq') and not quick
    if groq_keys and only in (None, 'groq'):
        model = settings.get('GROQ_MODEL') or 'openai/gpt-oss-120b'
        clients.append(ModelClient(OpenAICompatAdapter(model=model), groq_keys, cache_dir,
                                   **{**options, **({'wait_when_limited': False} if overflow else {})}))
    if mistral_keys and (overflow or only == 'mistral'):
        clients.append(ModelClient(mistral(settings.get('MISTRAL_MODEL')), mistral_keys, cache_dir, **options))
    if settings.get('OLLAMA_MODEL') and only in (None, 'ollama'):
        clients.append(ModelClient(OllamaAdapter(settings['OLLAMA_MODEL'], settings.get('OLLAMA_HOST', 'http://localhost:11434')), ['local'], cache_dir, **options))
    if not clients:
        raise ValueError('no configured provider')
    return FallbackClient(clients, budget=(budget or 25) if quick else None)
