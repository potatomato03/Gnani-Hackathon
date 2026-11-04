import io
import wave

import pytest

from voicerx.agent.conversation import advance, start
from voicerx.agent.demo import build_visit
from voicerx.agent.templates import load_templates
from voicerx.agent.voice import (VoiceRefused, check_wav, repair_wav_sizes, synthetic_voice_note,
                                  transcribe_voice_note, voice_message)
from voicerx.ingest.gnani import Transcript


def wav(seconds=1.0, rate=16000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


class FakeSpeech:
    """Stands in for Gnani: no network, no credits."""

    def __init__(self, transcript=""):
        self.transcript = transcript
        self.calls = []

    def transcribe(self, wav_bytes, language_code):
        self.calls.append(("transcribe", language_code, len(wav_bytes)))
        return Transcript(text=self.transcript, detected_language=None, truncated=False)

    def synthesize(self, text, language, voice, container="mp3", sample_rate=24000):
        self.calls.append(("synthesize", text, language, voice, container))
        return wav() if container == "wav" else b"ID3-fake-mp3"


@pytest.fixture(scope="module")
def visits(tmp_path_factory):
    out = tmp_path_factory.mktemp("visits")
    return {case: build_visit(case, out) for case in ("fam-001-a", "fam-010-a")}


@pytest.fixture
def asthma(visits):
    return start(visits["fam-010-a"], "c-voice")


def test_clinic_message_is_voiced_once_and_then_served_from_cache(asthma, tmp_path):
    speech = FakeSpeech()
    summary = asthma.messages[0]
    name, cached = voice_message(asthma, summary.id, speech, tmp_path)
    assert not cached and (tmp_path / f"{name}.mp3").read_bytes() == b"ID3-fake-mp3"
    assert speech.calls == [("synthesize", summary.text, "auto", "Chetana", "mp3")]   # exactly the gated text
    again, cached = voice_message(asthma, summary.id, speech, tmp_path)
    assert cached and again == name and len(speech.calls) == 1
    assert asthma.messages[0].audio_id == name


def test_only_clinic_messages_can_be_voiced(asthma, tmp_path):
    speech = FakeSpeech("Montair कब लेनी है?")
    transcribe_voice_note(asthma, wav(), speech)
    patient = [m for m in asthma.messages if m.sender == "patient"][0]
    with pytest.raises(VoiceRefused):
        voice_message(asthma, patient.id, speech, tmp_path)
    with pytest.raises(VoiceRefused):
        voice_message(asthma, "m999", speech, tmp_path)


def test_voice_note_transcript_goes_through_the_same_rules(asthma):
    speech = FakeSpeech("Montair कब लेनी है?")
    record = transcribe_voice_note(asthma, wav(2), speech)
    assert speech.calls == [("transcribe", "hi-IN,en-IN", len(wav(2)))]
    assert record.transcript_source == "prisma" and record.action == "answered"
    patient = [m for m in asthma.messages if m.sender == "patient"][-1]
    assert patient.voice is True and patient.text == "Montair कब लेनी है?"
    assert asthma.messages[-1].kind == "answer" and "MONTAIR" in asthma.messages[-1].text


def test_warning_sign_in_a_voice_note_is_urgent(asthma):
    transcribe_voice_note(asthma, wav(), FakeSpeech("सीने में दर्द हो रहा है"))
    assert asthma.messages[-1].kind == "urgent"
    assert [t.kind for t in asthma.tasks] == ["urgent"]
    assert "voice note" in asthma.tasks[0].note


def test_voice_answer_to_a_check_in_keeps_the_transcript_as_the_quote(asthma):
    advance(asthma)
    transcribe_voice_note(asthma, wav(), FakeSpeech("koi dikkat nahi"))
    answer = asthma.records[-1].answers[0]
    assert (answer.question, answer.value, answer.quote) == ("tolerance", "no_problem", "koi dikkat nahi")


def test_silence_asks_again_without_a_task(asthma):
    advance(asthma)
    transcribe_voice_note(asthma, wav(), FakeSpeech(""))
    reply = asthma.messages[-1]
    assert reply.text == load_templates("hi-IN")["replies"]["not_heard"]
    assert [b.id for b in reply.buttons] == ["no_problem", "some_problem", "stopped"]
    assert asthma.tasks == []


@pytest.mark.parametrize("clip, reason", [
    (wav(31), "longer than 30"),
    (b"not a wav at all", "not a WAV"),
    (b"\x00" * 3_000_001, "too large"),
])
def test_bad_clips_are_refused_before_any_call(asthma, clip, reason):
    speech = FakeSpeech("x")
    with pytest.raises(VoiceRefused, match=reason):
        transcribe_voice_note(asthma, clip, speech)
    assert speech.calls == []


def test_recorded_voice_is_never_written_to_disk(asthma, tmp_path):
    transcribe_voice_note(asthma, wav(), FakeSpeech("DOCTOR"))
    assert list(tmp_path.rglob("*")) == []


def test_synthetic_voice_note_uses_the_patient_voice_then_prisma(asthma, tmp_path):
    speech = FakeSpeech("Inhaler दिन में कितनी बार ले सकते हैं?")
    synthetic_voice_note(asthma, "Inhaler दिन में कितनी बार ले सकते हैं?", speech, tmp_path)
    assert speech.calls[0][:5] == ("synthesize", "Inhaler दिन में कितनी बार ले सकते हैं?", "auto", "Shubham", "wav")
    assert speech.calls[1][0] == "transcribe"
    assert asthma.messages[-1].kind == "answer" and "ASTHALIN" in asthma.messages[-1].text
    synthetic_voice_note(asthma, "Inhaler दिन में कितनी बार ले सकते हैं?", speech, tmp_path)
    assert [c[0] for c in speech.calls] == ["synthesize", "transcribe", "transcribe"]   # synthetic audio cached


def test_synthetic_text_limits(asthma, tmp_path):
    with pytest.raises(VoiceRefused):
        synthetic_voice_note(asthma, "  ", FakeSpeech(), tmp_path)
    with pytest.raises(VoiceRefused):
        synthetic_voice_note(asthma, "x" * 301, FakeSpeech(), tmp_path)


def test_english_patient_uses_english_hints(visits, tmp_path):
    english = build_visit("fam-004-a", tmp_path)
    conv = start(english, "c-en")
    speech = FakeSpeech("How often do I take Telma?")
    transcribe_voice_note(conv, wav(), speech)
    voice_message(conv, conv.messages[0].id, speech, tmp_path)
    assert speech.calls[0][1] == "en-IN,hi-IN" and speech.calls[1][2] == "en-IN"


def streaming_wav(seconds=1.0, rate=16000):
    """What Timbre returned in the live check (3 Nov): RIFF and data sizes left at 0xFFFFFFFF, as a stream."""
    clip = bytearray(wav(seconds, rate))
    clip[4:8] = b"\xff\xff\xff\xff"
    clip[40:44] = b"\xff\xff\xff\xff"
    return bytes(clip)


class StreamingSpeech(FakeSpeech):
    def synthesize(self, text, language, voice, container="mp3", sample_rate=24000):
        self.calls.append(("synthesize", text, language, voice, container))
        return streaming_wav(1.5) if container == "wav" else b"ID3-fake-mp3"


def test_streaming_wav_sizes_are_repaired_from_the_real_length():
    fixed = repair_wav_sizes(streaming_wav(1.5))
    assert check_wav(fixed) == pytest.approx(1.5)
    assert int.from_bytes(fixed[4:8], "little") == len(fixed) - 8
    assert repair_wav_sizes(wav(1.0)) == wav(1.0)   # a correct header is left alone


def test_synthetic_voice_note_accepts_timbre_streaming_wav(asthma, tmp_path):
    speech = StreamingSpeech("Montair कब लेनी है?")
    synthetic_voice_note(asthma, "Montair कब लेनी है?", speech, tmp_path)
    assert [c[0] for c in speech.calls] == ["synthesize", "transcribe"]
    assert asthma.messages[-1].kind == "answer" and "MONTAIR" in asthma.messages[-1].text
    cached = next(tmp_path.glob("*.wav")).read_bytes()
    assert check_wav(cached) == pytest.approx(1.5)   # cached with real sizes, so the browser can play it


def test_streaming_header_voice_note_is_measured_by_its_real_length(asthma):
    speech = FakeSpeech("Montair कब लेनी है?")
    transcribe_voice_note(asthma, streaming_wav(1.0), speech)
    assert speech.calls[0][0] == "transcribe"
    with pytest.raises(VoiceRefused, match="longer than 30"):
        transcribe_voice_note(asthma, streaming_wav(31), FakeSpeech("x"))
