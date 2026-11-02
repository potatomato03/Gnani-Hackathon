import json

import pytest
from pydantic import BaseModel

from voicerx.llm.client import (FallbackClient, ModelClient, ModelOutputInvalid, QuotaExhausted, build_client,
                                json_schema_for)
from voicerx.llm.gemini import GeminiAdapter
from voicerx.llm.ollama import OllamaAdapter


class Inner(BaseModel):
    word: str


class Outer(BaseModel):
    items: list[Inner]


def ollama_reply(obj, done_reason="stop", used=500):
    return 200, {}, json.dumps({"message": {"role": "assistant", "content": json.dumps(obj)},
                                "done_reason": done_reason, "prompt_eval_count": used, "eval_count": 100})


def gemini_reply(obj):
    return 200, {}, json.dumps({"steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(obj)}]}]})


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        return self.responses.pop(0)


def gemini(tmp_path, responses, keys=("g1",)):
    transport = FakeTransport(responses)
    return ModelClient(GeminiAdapter(), list(keys), tmp_path, transport=transport, sleep=lambda s: None), transport


def ollama(tmp_path, responses):
    transport = FakeTransport(responses)
    return ModelClient(OllamaAdapter(), ["local"], tmp_path, transport=transport, sleep=lambda s: None), transport


DAILY_LIMIT = (429, {}, '{"error": {"message": "Quota exceeded for requests per day"}}')


def test_schema_is_strict_and_has_no_references():
    schema = json_schema_for(Outer)
    item = schema["properties"]["items"]["items"]
    assert "$ref" not in json.dumps(schema)
    assert item["additionalProperties"] is False and item["required"] == ["word"]


def test_gemini_request_uses_the_interactions_api_with_a_schema():
    url, headers, body = GeminiAdapter().build("s", "u", json_schema_for(Outer), "g1")
    assert url.endswith("/v1beta/interactions") and headers["x-goog-api-key"] == "g1"
    assert body["response_format"]["mime_type"] == "application/json"


def test_ollama_request_enforces_the_schema_and_sends_no_key():
    url, headers, body = OllamaAdapter().build("s", "u", json_schema_for(Outer), "local")
    assert url == "http://localhost:11434/api/chat"
    assert "local" not in json.dumps(headers) and "Authorization" not in headers
    assert body["format"] == json_schema_for(Outer)
    assert body["stream"] is False and body["think"] is False and body["options"]["temperature"] == 0


def test_ollama_reply_length_is_capped_below_the_context():
    # qwen3:8b looped on fam-009-b, generating until the 8,192-token context filled (runbook C-38).
    _, _, body = OllamaAdapter().build("s", "u", json_schema_for(Outer), "local")
    assert body["options"]["num_predict"] == 4096 < body["options"]["num_ctx"]


def test_second_identical_call_is_served_from_the_cache(tmp_path):
    client, transport = gemini(tmp_path, [gemini_reply({"items": [{"word": "a"}]})])
    client.generate("s", "u", Outer, "v1")
    result, meta = client.generate("s", "u", Outer, "v1")
    assert result.items[0].word == "a" and meta.cached is True and len(transport.calls) == 1


def test_daily_limit_moves_to_the_second_key_without_retrying(tmp_path):
    client, transport = gemini(tmp_path, [DAILY_LIMIT, gemini_reply({"items": []})], keys=("g1", "g2"))
    _, meta = client.generate("s", "u", Outer, "v1")
    assert meta.key_index == 1 and len(transport.calls) == 2


def test_overloaded_provider_is_retried(tmp_path):
    client, transport = gemini(tmp_path, [(503, {}, "busy"), gemini_reply({"items": []})])
    _, meta = client.generate("s", "u", Outer, "v1")
    assert meta.attempts == 2


def test_fallback_moves_from_gemini_to_ollama(tmp_path):
    first, _ = gemini(tmp_path / "g", [DAILY_LIMIT])
    local, _ = ollama(tmp_path / "o", [ollama_reply({"items": []})])
    _, meta = FallbackClient([first, local]).generate("s", "u", Outer, "v1")
    assert meta.provider == "ollama"


def test_unreachable_server_is_exhausted_immediately(tmp_path):
    client, transport = ollama(tmp_path, [(0, {}, "connection refused")])
    with pytest.raises(QuotaExhausted):
        client.generate("s", "u", Outer, "v1")
    assert len(transport.calls) == 1


def test_timeout_is_a_retryable_error_but_a_refused_connection_is_unreachable(monkeypatch):
    import socket
    import urllib.error
    import urllib.request

    from voicerx.llm.client import transport

    def raise_(error):
        def urlopen(*args, **kwargs):
            raise error
        return urlopen

    monkeypatch.setattr(urllib.request, "urlopen", raise_(TimeoutError("timed out")))
    assert transport("http://x", {}, {})[0] == 504
    monkeypatch.setattr(urllib.request, "urlopen", raise_(urllib.error.URLError(socket.timeout("timed out"))))
    assert transport("http://x", {}, {})[0] == 504
    monkeypatch.setattr(urllib.request, "urlopen", raise_(urllib.error.URLError(ConnectionRefusedError())))
    assert transport("http://x", {}, {})[0] == 0


def test_slow_reply_is_retried_on_the_same_key(tmp_path):
    client, transport = gemini(tmp_path, [(504, {}, "timed out"), gemini_reply({"items": []})], keys=("g1", "g2"))
    _, meta = client.generate("s", "u", Outer, "v1")
    assert meta.key_index == 0 and meta.attempts == 2


def test_model_not_pulled_is_exhausted_immediately(tmp_path):
    client, transport = ollama(tmp_path, [(404, {}, '{"error":"model \'qwen3:8b\' not found"}')])
    with pytest.raises(QuotaExhausted):
        client.generate("s", "u", Outer, "v1")
    assert len(transport.calls) == 1


def test_cut_off_or_overflowing_reply_is_never_accepted(tmp_path):
    client, _ = ollama(tmp_path, [ollama_reply({"items": []}, done_reason="length"),
                                  ollama_reply({"items": []}, used=8100)])
    with pytest.raises(ModelOutputInvalid):
        client.generate("s", "u", Outer, "v1")


def test_invalid_reply_gets_one_repair_attempt(tmp_path):
    client, _ = ollama(tmp_path, [ollama_reply({"wrong": 1}), ollama_reply({"items": []})])
    result, meta = client.generate("s", "u", Outer, "v1")
    assert result.items == [] and meta.attempts == 2


def test_two_invalid_replies_raise(tmp_path):
    client, _ = ollama(tmp_path, [ollama_reply({"wrong": 1}), ollama_reply({"wrong": 2})])
    with pytest.raises(ModelOutputInvalid):
        client.generate("s", "u", Outer, "v1")


def test_cache_files_never_contain_a_key(tmp_path):
    client, _ = gemini(tmp_path, [gemini_reply({"items": []})], keys=("SECRET-KEY-VALUE",))
    client.generate("s", "u", Outer, "v1")
    assert all("SECRET-KEY-VALUE" not in p.read_text(encoding="utf-8") for p in tmp_path.glob("*.json"))


def test_build_client_orders_gemini_before_ollama_and_can_keep_one(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=g1\nGEMINI_API_KEY_2=\nOLLAMA_MODEL=qwen3:8b\n", encoding="utf-8")
    assert [c.adapter.name for c in build_client(env, tmp_path).clients] == ["gemini", "ollama"]
    assert [c.adapter.name for c in build_client(env, tmp_path, only="ollama").clients] == ["ollama"]
def test_concurrent_identical_cloud_replies_leave_a_valid_cache(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    def transport(*args):
        barrier.wait(timeout=5)
        return gemini_reply({'items': [{'word': 'cached'}]})
    client = ModelClient(GeminiAdapter(), ['g1'], tmp_path, transport=transport)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.generate('s', 'u', Outer, 'v1'), range(2)))
    assert all(result.items[0].word == 'cached' for result, _ in results)
    result, meta = client.generate('s', 'u', Outer, 'v1')
    assert meta.cached and result.items[0].word == 'cached'




def groq_reply(obj, finish_reason="stop"):
    return 200, {}, json.dumps({"choices": [{"message": {"role": "assistant", "content": json.dumps(obj)},
                                             "finish_reason": finish_reason}]})


def groq(tmp_path, responses):
    from voicerx.llm.openai_compat import OpenAICompatAdapter

    transport = FakeTransport(responses)
    return ModelClient(OpenAICompatAdapter(), ["q1"], tmp_path, transport=transport, sleep=lambda s: None), transport


def test_groq_request_enforces_a_strict_schema():
    from voicerx.llm.openai_compat import OpenAICompatAdapter

    url, headers, body = OpenAICompatAdapter().build("s", "u", json_schema_for(Outer), "q1")
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer q1" and body["model"] == "openai/gpt-oss-120b"
    assert body["temperature"] == 0
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == json_schema_for(Outer)


def test_groq_rejected_json_gets_the_repair_attempt(tmp_path):
    rejected = (400, {}, '{"error":{"code":"json_validate_failed","message":"Failed to generate JSON."}}')
    client, transport = groq(tmp_path, [rejected, groq_reply({"items": []})])
    result, meta = client.generate("s", "u", Outer, "v1")
    assert result.items == [] and meta.attempts == 2 and meta.provider == "groq"


def test_groq_other_client_errors_are_not_repaired(tmp_path):
    client, _ = groq(tmp_path, [(400, {}, '{"error":{"code":"model_not_found"}}')])
    with pytest.raises(ModelOutputInvalid):
        client.generate("s", "u", Outer, "v1")


def test_groq_cut_off_reply_is_never_accepted(tmp_path):
    client, _ = groq(tmp_path, [groq_reply({"items": []}, "length"), groq_reply({"items": []}, "length")])
    with pytest.raises(ModelOutputInvalid):
        client.generate("s", "u", Outer, "v1")


def test_groq_daily_limit_is_exhausted_without_retrying(tmp_path):
    daily = (429, {"retry-after": "600"}, '{"error":{"message":"Rate limit reached on tokens per day (TPD)"}}')
    client, transport = groq(tmp_path, [daily])
    with pytest.raises(QuotaExhausted):
        client.generate("s", "u", Outer, "v1")
    assert len(transport.calls) == 1


def test_build_client_puts_groq_between_gemini_and_ollama(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=g1\nGROQ_API_KEY=q1\nOLLAMA_MODEL=qwen3:8b\n", encoding="utf-8")
    assert [c.adapter.name for c in build_client(env, tmp_path).clients] == ["gemini", "groq", "ollama"]
    assert [c.adapter.name for c in build_client(env, tmp_path, only="groq").clients] == ["groq"]


def test_build_client_uses_both_groq_keys_in_order(tmp_path):
    # Each Groq key belongs to its own organisation with its own daily token limit (runbook D-88).
    env = tmp_path / ".env"
    env.write_text("GROQ_API_KEY=q1\nGROQ_API_KEY_2=q2\n", encoding="utf-8")
    assert build_client(env, tmp_path, only="groq").clients[0].keys == ["q1", "q2"]
