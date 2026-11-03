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
                 timeout=300, cooldown=None, clock=time.monotonic):
        """max_transient: tries per key on 429/5xx. A chat message uses 1 and a short timeout, so a busy
        provider falls back to the rules in seconds instead of minutes (runbook D-115). cooldown: seconds a
        key that was busy or unreachable rests before it is tried again; None means for the rest of the run.
        A daily quota always ends the key for the run."""
        self.adapter, self.keys, self.cache_dir = adapter, keys, Path(cache_dir)
        self.max_transient, self.timeout, self.cooldown, self.clock = max_transient, timeout, cooldown, clock
        self.transport = transport or partial(globals()['transport'], timeout=timeout)
        self.sleep = sleep
        self.exhausted = set()
        self.resting = {}           # key index -> clock time it may be tried again

    def _rest(self, index):
        if self.cooldown is None:
            self.exhausted.add(index)
        else:
            self.resting[index] = self.clock() + self.cooldown

    def generate(self, system, user, schema, prompt_version):
        if self.adapter.name == 'ollama':
            with _LOCAL_LOCK:
                return self._generate(system, user, schema, prompt_version)
        return self._generate(system, user, schema, prompt_version)

    def _generate(self, system, user, schema, prompt_version):
        fingerprint = json.dumps([self.adapter.name, self.adapter.model, prompt_version, system, user], ensure_ascii=False)
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
        for index, key in enumerate(self.keys):
            if index in self.exhausted or self.resting.get(index, 0) > self.clock():
                continue
            transient = 0
            while transient < self.max_transient:
                url, headers, body = self.adapter.build(system, request_user, json_schema_for(schema), key)
                status, response_headers, text = self.transport(url, headers, body)
                attempts += 1
                if self.adapter.is_quota_exhausted(status, response_headers, text):
                    self.exhausted.add(index)
                    break
                if status == 0:
                    self._rest(index)
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
                    if repair:
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
                return parsed, meta
        raise QuotaExhausted(f'{self.adapter.name}: no available key or server')


class FallbackClient:
    def __init__(self, clients):
        self.clients = clients

    def generate(self, system, user, schema, prompt_version):
        for client in self.clients:
            try:
                return client.generate(system, user, schema, prompt_version)
            except QuotaExhausted:
                continue
        raise QuotaExhausted('all configured providers unavailable')


def build_client(env_path: Path, cache_dir: Path, only=None, quick=False):
    """quick=True is for chat messages: one try per key, a 15 s timeout, no waiting, and a second Gemini
    model when the first is busy (gemini-3.8-flash returned 503 "high demand" on 4 Nov)."""
    from .gemini import DEFAULT_MODEL, GeminiAdapter
    from .ollama import OllamaAdapter
    from .openai_compat import OpenAICompatAdapter
    settings = {}
    for line in env_path.read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            settings[key.strip()] = value.strip().strip('\"\'')
    options = {'max_transient': 1, 'timeout': 15, 'cooldown': 60, 'sleep': lambda seconds: None} if quick else {}
    clients = []
    keys = [settings[k] for k in ('GEMINI_API_KEY', 'GEMINI_API_KEY_2') if settings.get(k)]
    if keys and only in (None, 'gemini'):
        fallback = settings.get('GEMINI_FALLBACK_MODEL') or (QUICK_FALLBACK if quick else '')
        models = list(dict.fromkeys([settings.get('GEMINI_MODEL') or DEFAULT_MODEL,
                                     *filter(None, (m.strip() for m in fallback.split(',')))]))
        clients.extend(ModelClient(GeminiAdapter(model), keys, cache_dir, **options) for model in models)
    groq_keys = [settings[k] for k in ('GROQ_API_KEY', 'GROQ_API_KEY_2') if settings.get(k)]
    if groq_keys and only in (None, 'groq'):
        model = settings.get('GROQ_MODEL') or 'openai/gpt-oss-120b'
        clients.append(ModelClient(OpenAICompatAdapter(model=model), groq_keys, cache_dir, **options))
    if settings.get('OLLAMA_MODEL') and only in (None, 'ollama'):
        clients.append(ModelClient(OllamaAdapter(settings['OLLAMA_MODEL'], settings.get('OLLAMA_HOST', 'http://localhost:11434')), ['local'], cache_dir, **options))
    if not clients:
        raise ValueError('no configured provider')
    return FallbackClient(clients)
