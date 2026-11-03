"""WhatsApp voice calls: the patient calls the clinic's number and talks to the same agent (runbook D-114).

Turn-taking is half-duplex. The agent speaks, listens for one utterance, sends it to Prisma, and passes the
transcript through exactly the same routing, red flags and gate as a typed message. Then it speaks the gated
replies with Timbre. There's no barge-in: the patient is not heard while the agent speaks.

Call audio is held in memory one utterance at a time and never written (the challenge bans recorded calls,
and D-111 keeps no recording). Spoken replies are synthetic clinic text, cached by content like Listen.
The media side (WebRTC) is behind CallAudio, so the loop is testable without a network.
"""
import asyncio
import io
import time
import wave
from array import array
from pathlib import Path
from typing import Protocol

from ..ingest.gnani import CLINIC_VOICE, TTS_MODEL, stt_languages, tts_language
from .templates import load_templates

RATE = 16000                 # what the VAD and Prisma get
FRAME_SAMPLES = 320          # 20 ms at 16 kHz
MAX_TURNS = 6
MAX_CALL_SECONDS = 300
LISTEN_SECONDS = 12          # silence before the agent prompts again
SPEECH_RATE = 24000          # Timbre WAV for the call


class CallAudio(Protocol):
    hung_up: bool

    async def listen(self, timeout: float) -> bytes | None:
        """One utterance as 16 kHz mono 16-bit PCM, or None after `timeout` seconds of silence or a hang-up."""

    async def speak(self, wav: bytes) -> None:
        """Play a WAV to the caller and return when it has been played."""


class Utterances:
    """Energy voice-activity detection on 16 kHz mono 16-bit PCM.

    An utterance starts when a 20 ms frame's RMS is above `threshold`, keeps 0.3 s of audio from before the
    start, and ends after `end_silence` seconds of quiet or at `max_seconds`. Shorter bursts than
    `min_speech` seconds (a click, a cough) are dropped.
    """

    def __init__(self, threshold=500, end_silence=0.8, max_seconds=25.0, min_speech=0.25):
        self.threshold, self.max_seconds, self.min_speech = threshold, max_seconds, min_speech
        self.end_frames = int(end_silence * RATE / FRAME_SAMPLES)
        self.preroll = int(0.3 * RATE / FRAME_SAMPLES)
        self.reset()

    def reset(self):
        self._pending = b''
        self._before: list[bytes] = []
        self._frames: list[bytes] = []
        self._voiced = 0
        self._quiet = 0

    def feed(self, pcm: bytes) -> bytes | None:
        self._pending += pcm
        size = FRAME_SAMPLES * 2
        done = None
        while len(self._pending) >= size and done is None:
            frame, self._pending = self._pending[:size], self._pending[size:]
            done = self._frame(frame)
        return done

    def _frame(self, frame):
        samples = array('h', frame)
        loud = (sum(s * s for s in samples) / len(samples)) ** 0.5 > self.threshold
        if not self._frames:
            if not loud:
                self._before = (self._before + [frame])[-self.preroll:]
                return None
            self._frames, self._before = self._before + [frame], []
            self._voiced, self._quiet = 1, 0
            return None
        self._frames.append(frame)
        if loud:
            self._voiced, self._quiet = self._voiced + 1, 0
        else:
            self._quiet += 1
        seconds = len(self._frames) * FRAME_SAMPLES / RATE
        if self._quiet >= self.end_frames or seconds >= self.max_seconds:
            utterance, voiced = b''.join(self._frames), self._voiced
            self.reset()
            if voiced * FRAME_SAMPLES / RATE < self.min_speech:
                return None
            return utterance
        return None


def pcm_to_wav(pcm: bytes, rate=RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm)
    return buffer.getvalue()


def call_texts(conv):
    templates = load_templates(conv.language)['call']
    names = {'doctor': conv.doctor_name, 'clinic': conv.clinic_name}
    return {key: text.format(**names) for key, text in templates.items()}


async def speak_text(audio: CallAudio, text, language, speech, cache_dir: Path):
    """Timbre speaks exactly this text; the WAV is cached by content, so repeated replies cost nothing."""
    from .voice import cache_name, repair_wav_sizes
    tts = tts_language(language)
    path = Path(cache_dir) / f'{cache_name(TTS_MODEL, CLINIC_VOICE, tts, "wav24k", text)}.wav'
    if not path.exists():
        wav = await asyncio.to_thread(speech.synthesize, text, tts, CLINIC_VOICE, container='wav',
                                      sample_rate=SPEECH_RATE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(repair_wav_sizes(wav))
    await audio.speak(path.read_bytes())


async def run_call(conv, audio: CallAudio, speech, cache_dir: Path, respond, max_turns=MAX_TURNS,
                   max_seconds=MAX_CALL_SECONDS, listen_seconds=LISTEN_SECONDS, clock=time.monotonic) -> str:
    """Talk with the patient until they hang up, the agent ends the call, or a limit is reached.

    respond(text) passes one transcript through the conversation (under the app's lock) and returns
    (clinic texts to speak, whether the call should end). Returns why the call ended.
    """
    texts = call_texts(conv)
    started = clock()
    await speak_text(audio, texts['greeting'], conv.language, speech, cache_dir)
    silent = 0
    for _ in range(max_turns):
        if audio.hung_up:
            return 'hung_up'
        if clock() - started > max_seconds:
            break
        pcm = await audio.listen(listen_seconds)
        if audio.hung_up:
            return 'hung_up'
        if pcm is None:
            silent += 1
            if silent >= 2:
                break
            await speak_text(audio, texts['no_input'], conv.language, speech, cache_dir)
            continue
        silent = 0
        transcript = await asyncio.to_thread(speech.transcribe, pcm_to_wav(pcm), stt_languages(conv.language))
        del pcm   # the caller's audio is not kept past this point
        replies, end = await asyncio.to_thread(respond, transcript.text)
        for reply in replies:
            await speak_text(audio, reply, conv.language, speech, cache_dir)
        if end:
            return 'ended_by_agent'
    if not audio.hung_up:
        await speak_text(audio, texts['goodbye'], conv.language, speech, cache_dir)
    return 'limit'


def call_turn(conv, text, nlu=None):
    """One thing the caller said, through the same rules as a typed message.

    Returns (the gated clinic replies to speak, whether to end the call). The call ends after a warning sign
    (the urgent reply tells the patient to go to emergency or call 108), after STOP, and after DOCTOR.
    """
    from .conversation import receive
    from .gate import GateRefused
    messages, tasks = len(conv.messages), len(conv.tasks)
    try:
        record = receive(conv, text=text, source='call', nlu=nlu)
    except GateRefused:
        return [], True
    replies = [m.text for m in conv.messages[messages:] if m.sender == 'clinic']
    end = record.action in ('urgent', 'stopped') or any(t.kind == 'callback' for t in conv.tasks[tasks:])
    return replies, end
