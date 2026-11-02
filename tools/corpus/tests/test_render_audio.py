import base64
import io
import json
import math
import struct
import wave

import pytest

pytest.importorskip("av")

from check_cases import sha256  # noqa: E402
from render_audio import (  # noqa: E402
    build_request,
    cases_from_family,
    find_audio,
    is_daily_limit,
    next_model,
    pending,
    retry_delay,
    script_hash,
    to_16k,
    voices_for,
)


def tone_wav(rate, seconds=1.0, channels=1):
    frames = bytearray()
    for index in range(int(rate * seconds)):
        sample = int(12000 * math.sin(2 * math.pi * 440 * index / rate))
        frames += struct.pack("<h", sample) * channels
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(channels)
        clip.setsampwidth(2)
        clip.setframerate(rate)
        clip.writeframes(bytes(frames))
    return buffer.getvalue()


def shape(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as clip:
        return clip.getframerate(), clip.getnchannels(), clip.getsampwidth(), clip.getnframes()


def family():
    return {
        "family_id": "fam-900",
        "language": "hinglish",
        "encounters": [
            {
                "encounter_id": "e1",
                "doctor_id": "doc-002",
                "variants": [
                    {
                        "variant_id": "fam-900-a",
                        "utterances": [
                            {"id": "u1", "speaker": "doctor", "text": "पहली लाइन।"},
                            {"id": "u2", "speaker": "patient", "text": "दूसरी लाइन।"},
                        ],
                    }
                ],
            }
        ],
    }


def test_doctor_only_script_is_one_voice_reading_one_text():
    lines = [("doctor", "First line."), ("doctor", "Second line.")]
    body = build_request(lines, {"doctor": "Charon"})
    assert body["generation_config"]["speech_config"] == [{"voice": "Charon"}]
    content = body["input"][0]["content"]
    assert len(content) == 1
    assert content[0]["text"] == "First line. Second line."


def test_two_speaker_script_labels_every_turn_with_its_speaker():
    lines = [("doctor", "Dictating."), ("patient", "Interrupting."), ("doctor", "Dictating again.")]
    body = build_request(lines, {"doctor": "Charon", "patient": "Aoede"})
    speakers = body["generation_config"]["speech_config"]["speakers"]
    assert {(item["speaker"], item["voice"]) for item in speakers} == {("doctor", "Charon"), ("patient", "Aoede")}
    content = body["input"][0]["content"]
    assert [item["text"] for item in content] == ["Dictating.", "Interrupting.", "Dictating again."]
    assert [item["annotations"][0]["speaker"] for item in content] == ["doctor", "patient", "doctor"]


def test_more_than_two_speakers_is_refused_because_gemini_cannot_render_it():
    lines = [("doctor", "a"), ("patient", "b"), ("other", "c")]
    with pytest.raises(ValueError):
        build_request(lines, {"doctor": "Charon", "patient": "Aoede", "other": "Puck"})


def test_each_doctor_gets_a_different_voice_from_the_others_and_the_patient():
    voices = [voices_for(doctor)["doctor"] for doctor in ("doc-001", "doc-002", "doc-003")]
    assert len(set(voices)) == 3
    assert voices_for("doc-001")["patient"] not in voices


def test_unknown_doctor_is_refused_rather_than_given_a_default_voice():
    with pytest.raises(KeyError):
        voices_for("doc-999")


def test_cases_come_from_every_variant_with_their_doctor_and_lines():
    cases = cases_from_family(family())
    assert [case["case_id"] for case in cases] == ["fam-900-a"]
    assert cases[0]["doctor_id"] == "doc-002"
    assert cases[0]["language"] == "hinglish"
    assert cases[0]["lines"] == [("doctor", "पहली लाइन।"), ("patient", "दूसरी लाइन।")]


def test_script_hash_matches_the_manifest_transcript_hash():
    lines = [("doctor", "One."), ("patient", "Two.")]
    assert script_hash(lines) == sha256("[doctor] One.\n[patient] Two.")


def test_audio_is_found_in_the_model_output_step():
    reply = {
        "steps": [
            {"type": "thought", "content": [{"type": "text", "text": "ignored"}]},
            {"type": "model_output", "content": [{"type": "audio", "data": "QUJD", "mime_type": "audio/wav"}]},
        ]
    }
    assert find_audio(reply) == b"ABC"


def test_reply_without_audio_gives_none():
    assert find_audio({"steps": [{"type": "model_output", "content": [{"type": "text"}]}]}) is None


def test_gemini_24k_audio_becomes_16k_mono_16_bit():
    rate, channels, width, frames = shape(to_16k(tone_wav(24000)))
    assert (rate, channels, width) == (16000, 1, 2)
    assert abs(frames - 16000) < 400


def test_stereo_audio_becomes_mono():
    assert shape(to_16k(tone_wav(24000, channels=2)))[1] == 1


def test_audio_already_at_16k_mono_is_left_untouched():
    original = tone_wav(16000)
    assert to_16k(original) == original


def quota_error(quota_id, delay=None):
    details = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota_id}]}]
    if delay:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay})
    return json.dumps({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": details}})


def test_retry_wait_comes_from_the_error():
    assert retry_delay(quota_error("GenerateRequestsPerMinute", "34s"), default=5) == 35


def test_fractional_retry_wait_is_rounded_up():
    assert retry_delay(quota_error("GenerateRequestsPerMinute", "1.2s"), default=5) == 3


def test_retry_wait_falls_back_when_the_error_gives_none():
    assert retry_delay("not json", default=7) == 7


def test_daily_quota_is_recognised():
    assert is_daily_limit(quota_error("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))


GOOGLE_DAILY_LIMIT = (
    '{"error":{"message":"Rate limit exceeded for model gemini-3.8-flash-tts (limit: 10 requests per day '
    'on Free Tier). Please retry in 40m9s or upgrade your tier.","code":"too_many_requests"}}'
)


def test_daily_limit_worded_in_the_message_is_recognised():
    assert is_daily_limit(GOOGLE_DAILY_LIMIT)


def test_retry_after_header_is_used_when_the_body_gives_no_delay():
    assert retry_delay("{}", default=5, retry_after="12") == 13


def test_request_names_the_model_it_was_built_for():
    body = build_request([("doctor", "Text.")], {"doctor": "Charon"}, model="gemini-3.8-flash-lite-tts")
    assert body["model"] == "gemini-3.8-flash-lite-tts"


def test_next_model_skips_models_that_ran_out_today():
    models = ["first", "second", "third"]
    assert next_model(models, set()) == "first"
    assert next_model(models, {"first"}) == "second"
    assert next_model(models, {"first", "second", "third"}) is None


def test_minute_quota_is_not_a_daily_limit():
    assert not is_daily_limit(quota_error("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "20s"))


def case(case_id="fam-900-a", lines=(("doctor", "One."),)):
    return {"case_id": case_id, "lines": list(lines)}


def test_rendered_clip_with_the_same_script_is_skipped():
    current = case()
    index = {"fam-900-a": {"script_hash": script_hash(current["lines"])}}
    assert pending([current], index, {"fam-900-a"}) == []


def test_changed_script_is_rendered_again():
    index = {"fam-900-a": {"script_hash": "old"}}
    assert [item["case_id"] for item in pending([case()], index, {"fam-900-a"})] == ["fam-900-a"]


def test_indexed_clip_missing_from_disk_is_rendered_again():
    current = case()
    index = {"fam-900-a": {"script_hash": script_hash(current["lines"])}}
    assert [item["case_id"] for item in pending([current], index, set())] == ["fam-900-a"]


def test_every_case_language_has_a_whisper_language_code():
    from typing import get_args

    from case_schema import Language
    from transcribe_audio import LANGUAGE_CODES

    assert set(LANGUAGE_CODES) == set(get_args(Language))


def test_text_ending_in_a_broken_character_is_flagged_as_truncated():
    from transcribe_audio import looks_truncated

    assert looks_truncated([120], "रात का खाना जल�")


def test_chunk_that_hit_the_token_cap_is_flagged_as_truncated():
    from transcribe_audio import looks_truncated

    assert looks_truncated([60, 224], "complete looking text")


def test_complete_transcript_is_not_flagged():
    from transcribe_audio import looks_truncated

    assert not looks_truncated([137, 61, 44], "तीन दिन में ठीक ना हो तो दुबारा दिखाना है")


def test_key_never_appears_in_the_request_body():
    body = build_request([("doctor", "Text.")], {"doctor": "Charon"})
    assert "key" not in json.dumps(body).lower()


def test_audio_reply_round_trips_through_base64():
    payload = base64.b64encode(tone_wav(24000, seconds=0.1)).decode()
    reply = {"steps": [{"type": "model_output", "content": [{"type": "audio", "data": payload}]}]}
    assert shape(find_audio(reply))[0] == 24000
