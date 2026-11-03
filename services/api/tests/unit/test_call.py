"""WhatsApp call loop and voice-activity detection, with scripted audio and a fake speech client.

No network, no Meta, no Gnani credits. Everything said is synthetic.
"""
import asyncio
import io
import math
import struct
import wave

import pytest

from voicerx.agent.call import RATE, Utterances, call_texts, call_turn, run_call
from voicerx.agent.conversation import start
from voicerx.agent.demo import build_visit
from voicerx.ingest.gnani import Transcript


def tone(seconds, amplitude=6000, hz=440):
    return b"".join(struct.pack("<h", int(amplitude * math.sin(2 * math.pi * hz * i / RATE)))
                    for i in range(int(seconds * RATE)))


def silence(seconds):
    return b"\x00\x00" * int(seconds * RATE)


def wav(seconds=0.2, rate=24000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


class FakeSpeech:
    def __init__(self, transcripts=()):
        self.transcripts, self.calls = list(transcripts), []

    def transcribe(self, audio, language_code, filename="voice-note.wav"):
        self.calls.append(("transcribe", language_code))
        return Transcript(text=self.transcripts.pop(0), detected_language=None, truncated=False)

    def synthesize(self, text, language, voice, container="mp3", sample_rate=24000):
        self.calls.append(("synthesize", text, container, sample_rate))
        return wav(rate=sample_rate)


class ScriptedCall:
    """The caller: says each utterance in turn (None = stays silent), then hangs up if told to."""

    def __init__(self, utterances, hang_up_after=None):
        self.utterances, self.hang_up_after = list(utterances), hang_up_after
        self.spoken, self.hung_up, self.heard = [], False, 0

    async def listen(self, timeout):
        if self.hang_up_after is not None and self.heard >= self.hang_up_after:
            self.hung_up = True
            return None
        self.heard += 1
        return self.utterances.pop(0) if self.utterances else None

    async def speak(self, data):
        assert data[:4] == b"RIFF"
        self.spoken.append(data)


@pytest.fixture(scope="module")
def visit(tmp_path_factory):
    return build_visit("fam-010-a", tmp_path_factory.mktemp("call-visits"))


@pytest.fixture
def conv(visit):
    return start(visit, "c-call")


def spoken_texts(speech):
    return [c[1] for c in speech.calls if c[0] == "synthesize"]


def call(conv, utterances, transcripts, cache, **limits):
    speech = FakeSpeech(transcripts)
    audio = ScriptedCall(utterances, limits.pop("hang_up_after", None))
    ended = asyncio.run(run_call(conv, audio, speech, cache, lambda text: call_turn(conv, text), **limits))
    return ended, speech, audio


# Voice-activity detection

def test_an_utterance_is_cut_at_the_silence_after_it():
    vad = Utterances()
    assert vad.feed(silence(1.0)) is None
    assert vad.feed(tone(1.0)) is None
    utterance = vad.feed(silence(1.0))
    assert utterance is not None and 1.0 <= len(utterance) / 2 / RATE <= 2.2


def test_silence_and_clicks_are_not_utterances():
    vad = Utterances()
    assert vad.feed(silence(3.0)) is None
    assert vad.feed(tone(0.06) + silence(1.0)) is None


def test_a_long_utterance_is_cut_at_25_seconds():
    utterance = Utterances().feed(tone(27.0))
    assert utterance is not None and len(utterance) / 2 / RATE == pytest.approx(25.0, abs=0.1)


# The call loop

def test_greeting_first_then_a_medicine_question_is_answered_from_the_approved_row(conv, tmp_path):
    ended, speech, audio = call(conv, [tone(1.0)], ["Montair कब लेनी है?"], tmp_path)
    texts = spoken_texts(speech)
    assert texts[0] == call_texts(conv)["greeting"] and "AI" in texts[0]
    assert "MONTAIR" in texts[1] and texts[1] == conv.messages[-1].text and conv.messages[-1].kind == "answer"
    patient = [m for m in conv.messages if m.sender == "patient"][-1]
    assert patient.voice and conv.records[-1].transcript_source == "prisma"
    assert ended == "limit" and texts[-1] == call_texts(conv)["goodbye"]
    assert all(c[2:] == ("wav", 24000) for c in speech.calls if c[0] == "synthesize")


def test_a_warning_sign_speaks_the_urgent_reply_and_ends_the_call(conv, tmp_path):
    ended, speech, _ = call(conv, [tone(1.0), tone(1.0)], ["seene mein dard ho raha hai", "unused"], tmp_path)
    assert ended == "ended_by_agent" and conv.messages[-1].kind == "urgent"
    assert spoken_texts(speech)[-1] == conv.messages[-1].text
    assert [t.kind for t in conv.tasks] == ["urgent"] and "WhatsApp call" in conv.tasks[0].note


def test_doctor_and_stop_end_the_call(visit, tmp_path):
    doctor = start(visit, "c-doctor")
    assert call(doctor, [tone(1.0)], ["DOCTOR"], tmp_path)[0] == "ended_by_agent"
    assert [t.kind for t in doctor.tasks] == ["callback"]
    stop = start(visit, "c-stop")
    assert call(stop, [tone(1.0)], ["STOP"], tmp_path)[0] == "ended_by_agent" and stop.stopped


def test_two_silences_get_one_prompt_then_goodbye(conv, tmp_path):
    ended, speech, _ = call(conv, [None, None], [], tmp_path)
    texts = call_texts(conv)
    assert spoken_texts(speech) == [texts["greeting"], texts["no_input"], texts["goodbye"]]
    assert ended == "limit" and not any(c[0] == "transcribe" for c in speech.calls)


def test_the_turn_cap_ends_the_call(conv, tmp_path):
    ended, speech, _ = call(conv, [tone(1.0)] * 5, ["Montair कब लेनी है?"] * 5, tmp_path, max_turns=3)
    assert sum(c[0] == "transcribe" for c in speech.calls) == 3 and ended == "limit"


def test_a_hang_up_stops_without_goodbye(conv, tmp_path):
    ended, speech, _ = call(conv, [tone(1.0)], ["Montair कब लेनी है?"], tmp_path, hang_up_after=1)
    assert ended == "hung_up" and call_texts(conv)["goodbye"] not in spoken_texts(speech)


def test_replies_are_cached_and_the_callers_audio_is_never_written(conv, tmp_path):
    caller = tone(1.0, amplitude=4321)
    call(conv, [caller], ["Montair कब लेनी है?"], tmp_path)
    _, again, _ = call(conv, [tone(1.0)], ["Montair कब लेनी है?"], tmp_path)
    assert not any(c[0] == "synthesize" for c in again.calls)     # greeting, answer and goodbye from cache
    for path in tmp_path.rglob("*"):
        assert path.suffix == ".wav" and caller[RATE:RATE + 64] not in path.read_bytes()


def test_call_wording_exists_in_every_language(conv):
    for key in ("greeting", "no_input", "goodbye"):
        assert call_texts(conv)[key]
