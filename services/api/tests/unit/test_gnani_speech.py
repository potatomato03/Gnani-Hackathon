import io
import json
import wave

import pytest

from voicerx.ingest import gnani
from voicerx.ingest.gnani import GnaniSpeech, SpeechError, speech_from_env

KEY = "test-key-not-real-0123456789"


def wav(seconds=1.0, rate=16000, channels=1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * int(seconds * rate) * channels)
    return buffer.getvalue()


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append({"url": url, "headers": headers, "body": body})
        return self.responses.pop(0)


def fields(body: bytes):
    """Read the plain multipart fields back out of a request body."""
    out = {}
    for part in body.split(b"--")[1:]:
        if b'name="' not in part:
            continue
        name = part.split(b'name="', 1)[1].split(b'"', 1)[0].decode()
        value = part.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0]
        out[name] = value if name == "audio_file" else value.decode()
    return out


def test_transcribe_sends_prisma_v3_codemix_with_the_key_only_in_its_header():
    reply = json.dumps({"success": True, "transcript": "ab theek hoon", "detected_language_code": "hi-IN"})
    transport = FakeTransport((200, {}, reply.encode()))
    speech = GnaniSpeech(KEY, transport=transport, sleep=lambda s: None)
    result = speech.transcribe(wav(), "hi-IN,en-IN")
    call = transport.calls[0]
    assert call["url"] == "https://api.vachana.ai/stt/v3"
    assert call["headers"]["X-API-Key-ID"] == KEY
    sent = fields(call["body"])
    assert sent["model"] == "prisma-v3.0" and sent["format"] == "codemix"
    assert sent["language_code"] == "hi-IN,en-IN"
    assert "keyterms" not in sent                       # runbook D-92
    assert b'filename="voice-note.wav"' in call["body"]  # Prisma reads the format from the extension
    assert result.text == "ab theek hoon" and result.detected_language == "hi-IN" and not result.truncated


def test_synthesize_posts_timbre_json_and_returns_the_audio_bytes():
    transport = FakeTransport((200, {"Content-Type": "audio/mpeg"}, b"ID3fake-mp3"))
    speech = GnaniSpeech(KEY, transport=transport, sleep=lambda s: None)
    audio = speech.synthesize("नमस्ते", "auto", "Chetana", container="mp3")
    call = transport.calls[0]
    assert call["url"] == "https://api.vachana.ai/api/v1/tts/inference"
    body = json.loads(call["body"])
    assert body["model"] == "timbre-v3.0" and body["voice"] == "Chetana" and body["language"] == "auto"
    assert body["text"] == "नमस्ते" and body["audio_config"]["container"] == "mp3"
    assert call["headers"]["Content-Type"] == "application/json"
    assert audio == b"ID3fake-mp3"


def test_rate_limit_is_retried_then_succeeds():
    busy = (429, {}, b'{"detail": {"error_code": "RATE_LIMITED"}}')
    transport = FakeTransport(busy, busy, (200, {}, b"RIFFok"))
    waits = []
    speech = GnaniSpeech(KEY, transport=transport, sleep=waits.append)
    assert speech.synthesize("hi", "en-IN", "Chetana") == b"RIFFok"
    assert len(transport.calls) == 3 and len(waits) == 2


def test_errors_carry_gnanis_message_but_never_the_key():
    transport = FakeTransport((401, {}, b'{"detail": {"error_code": "INVALID_API_KEY", "message": "Unauthorized"}}'))
    speech = GnaniSpeech(KEY, transport=transport, sleep=lambda s: None)
    with pytest.raises(SpeechError) as raised:
        speech.transcribe(wav(), "en-IN")
    assert raised.value.status == 401 and "Unauthorized" in str(raised.value)
    assert KEY not in str(raised.value) and KEY not in repr(raised.value)


def test_tts_error_shape_is_read_too():
    transport = FakeTransport((400, {}, b'{"success": false, "message": "Invalid request: voice"}'))
    with pytest.raises(SpeechError, match="Invalid request: voice"):
        GnaniSpeech(KEY, transport=transport, sleep=lambda s: None).synthesize("x", "en-IN", "Nobody")


def test_truncated_transcript_is_reported():
    reply = json.dumps({"success": True, "transcript": "cut", "truncated": True})
    speech = GnaniSpeech(KEY, transport=FakeTransport((200, {}, reply.encode())), sleep=lambda s: None)
    assert speech.transcribe(wav(), "en-IN").truncated is True


def test_key_comes_from_the_environment_or_dot_env(tmp_path, monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    assert speech_from_env(tmp_path / ".env") is None
    (tmp_path / ".env").write_text("OTHER=1\nGNANI_API_KEY= from-file \n", encoding="utf-8")
    assert speech_from_env(tmp_path / ".env").key == "from-file"
    monkeypatch.setenv("GNANI_API_KEY", "from-env")
    assert speech_from_env(tmp_path / ".env").key == "from-env"
    assert "from-env" not in repr(speech_from_env(tmp_path / ".env"))


def test_language_map_for_patients():
    assert gnani.stt_languages("hi-IN") == "hi-IN,en-IN"
    assert gnani.stt_languages("en-IN") == "en-IN,hi-IN"
    assert gnani.tts_language("hi-IN") == "auto"
    assert gnani.tts_language("en-IN") == "en-IN"
