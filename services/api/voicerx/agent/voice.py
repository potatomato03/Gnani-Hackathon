"""Voice notes for the follow-up chat (runbook D-111).

- Clinic messages: Timbre speaks exactly the text that already passed the gate, on demand, cached by content.
- Patient voice notes: Prisma transcribes them, and the transcript goes through the same rules as typed text.
  A recorded voice is never written to disk: only its transcript is kept.
- Synthetic voice notes: Timbre turns typed text into a patient voice, then Prisma transcribes it, so a demo
  needs no real person's voice (challenge rule). That audio is synthetic, so it may be cached.
"""
import hashlib
import io
import wave
from pathlib import Path

from ..contracts.followup import Conversation, FollowUpRecord
from ..ingest.gnani import CLINIC_VOICE, MAX_SECONDS, PATIENT_VOICE, TTS_MODEL, stt_languages, tts_language
from .conversation import receive, voice_not_used

MAX_BYTES = 3_000_000
MAX_SYNTHETIC_CHARS = 300


class VoiceRefused(Exception):
    pass


def repair_wav_sizes(data: bytes) -> bytes:
    """Timbre streams WAV with the RIFF and data sizes left at 0xFFFFFFFF (live check, 3 Nov 2026).

    Read as written, such a header claims hours of audio. Set both sizes from the bytes actually present, so
    the length check, Prisma and the browser all see the real clip. A correct header is returned unchanged.
    """
    if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        return data
    clip, offset = bytearray(data), 12
    while offset + 8 <= len(clip):
        size = int.from_bytes(clip[offset + 4:offset + 8], 'little')
        if clip[offset:offset + 4] == b'data':
            real = len(clip) - offset - 8
            if size > real:
                clip[offset + 4:offset + 8] = (real - real % 2).to_bytes(4, 'little')
            break
        offset += 8 + size + (size & 1)
    clip[4:8] = (len(clip) - 8).to_bytes(4, 'little')
    return bytes(clip)


def check_wav(data: bytes) -> float:
    if len(data) > MAX_BYTES:
        raise VoiceRefused('voice note is too large')
    try:
        with wave.open(io.BytesIO(data)) as clip:
            if clip.getcomptype() != 'NONE' or clip.getsampwidth() != 2 or clip.getnchannels() not in (1, 2) \
                    or not 8000 <= clip.getframerate() <= 48000:
                raise VoiceRefused('voice note must be 16-bit PCM WAV, mono or stereo, 8 to 48 kHz')
            seconds = clip.getnframes() / clip.getframerate()
    except (wave.Error, EOFError):
        raise VoiceRefused('voice note is not a WAV file') from None
    if seconds > MAX_SECONDS + 0.5:
        raise VoiceRefused(f'voice note is longer than {MAX_SECONDS} seconds')
    return seconds


def cache_name(*parts) -> str:
    return hashlib.sha256('\x1f'.join(parts).encode('utf-8')).hexdigest()[:32]


def _write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def voice_message(conv: Conversation, message_id: str, speech, cache_dir: Path):
    """Speak one clinic message already in the conversation. Returns (audio name, served from cache)."""
    message = next((m for m in conv.messages if m.id == message_id), None)
    if message is None or message.sender != 'clinic':
        raise VoiceRefused('only a message the clinic sent can be voiced')
    language = tts_language(conv.language)
    name = cache_name(TTS_MODEL, CLINIC_VOICE, language, 'mp3', message.text)
    path = Path(cache_dir) / f'{name}.mp3'
    cached = path.exists()
    if not cached:
        _write(path, speech.synthesize(message.text, language, CLINIC_VOICE, container='mp3'))
    message.audio_id = name
    return name, cached


def transcribe_voice_note(conv: Conversation, wav_bytes: bytes, speech, nlu=None) -> FollowUpRecord:
    if len(wav_bytes) > MAX_BYTES:
        raise VoiceRefused('voice note is too large')
    wav_bytes = repair_wav_sizes(wav_bytes)
    check_wav(wav_bytes)
    transcript = speech.transcribe(wav_bytes, stt_languages(conv.language))
    return receive(conv, text=transcript.text, source='prisma', nlu=nlu)


def ogg_opus_seconds(data: bytes) -> float:
    """Length of an Ogg Opus clip (a WhatsApp voice note): the last page's granule position, less the pre-skip
    in the OpusHead packet, at Opus's fixed 48 kHz granule rate. Raises ValueError for anything else."""
    head = data.find(b'OpusHead')
    last = data.rfind(b'OggS')
    if not data.startswith(b'OggS') or head < 0 or last < 0 or len(data) < last + 14 or len(data) < head + 12:
        raise ValueError('not an Ogg Opus file')
    pre_skip = int.from_bytes(data[head + 10:head + 12], 'little')
    granule = int.from_bytes(data[last + 6:last + 14], 'little', signed=True)
    return max(granule - pre_skip, 0) / 48000


def transcribe_ogg_voice_note(conv: Conversation, ogg_bytes: bytes, speech, nlu=None, command=None) -> FollowUpRecord:
    """A WhatsApp voice note (Ogg Opus) goes to Prisma as it is; Prisma reads ogg from the file name.
    A clip that is too long or not Ogg Opus gets a fixed reply and costs no Prisma call."""
    try:
        if len(ogg_bytes) > MAX_BYTES:
            raise VoiceRefused('voice note is too large')
        if ogg_opus_seconds(ogg_bytes) > MAX_SECONDS + 0.5:
            raise VoiceRefused(f'voice note is longer than {MAX_SECONDS} seconds')
    except (ValueError, VoiceRefused):
        return voice_not_used(conv)
    transcript = speech.transcribe(ogg_bytes, stt_languages(conv.language), filename='voice-note.ogg')
    if command and command(transcript.text):
        return conv.records[-1]
    return receive(conv, text=transcript.text, source='prisma', nlu=nlu)


def synthetic_voice_note(conv: Conversation, text: str, speech, cache_dir: Path, nlu=None) -> FollowUpRecord:
    text = text.strip()
    if not text or len(text) > MAX_SYNTHETIC_CHARS:
        raise VoiceRefused(f'synthetic voice note needs 1 to {MAX_SYNTHETIC_CHARS} characters of text')
    language = tts_language(conv.language)
    path = Path(cache_dir) / f'{cache_name(TTS_MODEL, PATIENT_VOICE, language, "wav16k", text)}.wav'
    if not path.exists():
        _write(path, repair_wav_sizes(speech.synthesize(text, language, PATIENT_VOICE, container='wav',
                                                        sample_rate=16000)))
    return transcribe_voice_note(conv, path.read_bytes(), speech, nlu)
