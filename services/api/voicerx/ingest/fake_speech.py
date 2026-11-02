"""A stand-in for Gnani used only by tests and the offline browser check (VOICERX_FAKE_SPEECH=1).

It makes no network call and spends no credits. It returns a short silent clip for speech, and for a
voice note it returns the text that was last synthesised as a patient voice, so the synthetic voice-note
path can be exercised end to end. It is never used when a real key is configured.
"""
import io
import wave

from .gnani import PATIENT_VOICE, Transcript


def silent_wav(seconds=0.5, rate=16000):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b'\x00\x00' * int(seconds * rate))
    return buffer.getvalue()


class FakeSpeech:
    name = 'fake'

    def __init__(self, transcript=''):
        self.transcript, self.calls = transcript, []

    def synthesize(self, text, language, voice, container='mp3', sample_rate=24000):
        self.calls.append(('synthesize', text, language, voice, container))
        if voice == PATIENT_VOICE:
            self.transcript = text
        return silent_wav(rate=sample_rate)  # a WAV even when mp3 is asked for; served by its real type

    def transcribe(self, wav_bytes, language_code):
        self.calls.append(('transcribe', language_code, len(wav_bytes)))
        return Transcript(text=self.transcript, detected_language=None, truncated=False)
