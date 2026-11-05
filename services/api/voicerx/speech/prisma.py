"""Gnani Prisma v3.0 speech-to-text over REST (runbook D-91, D-92).

The REST endpoint takes at most 30 seconds of audio a request. Longer recordings are cut in their
quietest moment before 29 seconds, and each piece goes with the text before it (`previous_text`),
so nothing is truncated to fit. `codemix` writes English words, brand names included, in Latin
script. No keyterms: they can turn an ambiguous brand into a specific product (D-92).
"""
import io
import json
import urllib.error
import urllib.request
import uuid
import wave

import numpy

URL = 'https://api.vachana.ai/stt/v3'
RATE = 16000
LIMIT_SECONDS = 29
EARLIEST_CUT = 18
# Gujarati goes with English, as Hinglish does, so English medicine names stay in Latin letters (D-121).
LANGUAGE_CODES = {'english': 'en-IN', 'hindi': 'hi-IN', 'hinglish': 'hi-IN,en-IN', 'tamil': 'ta-IN', 'telugu': 'te-IN',
                  'gujarati': 'gu-IN,en-IN'}
PREVIOUS_TEXT = 600


class PrismaError(Exception):
    def __init__(self, message, transient=False):
        super().__init__(message)
        self.transient = transient


def decode_audio(data):
    """Any container the browser or a file may hold (WebM/Opus, WAV, MP3, M4A), as 16 kHz mono float32."""
    import av
    resampler = av.AudioResampler(format='flt', layout='mono', rate=RATE)
    chunks = []
    with av.open(io.BytesIO(data)) as container:
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    return numpy.concatenate(chunks).astype(numpy.float32) if chunks else numpy.zeros(0, dtype=numpy.float32)


def wav_bytes(samples):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((numpy.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())
    return buffer.getvalue()


def segments(samples):
    """(start, end) sample ranges, each at most 29 seconds, cut where the audio is quietest."""
    limit, earliest, window = LIMIT_SECONDS * RATE, EARLIEST_CUT * RATE, RATE // 4
    parts, start = [], 0
    while len(samples) - start > limit:
        search = samples[start + earliest:start + limit]
        energy = numpy.convolve(numpy.abs(search), numpy.ones(window) / window, mode='valid')
        cut = start + earliest + int(numpy.argmin(energy)) + window // 2
        parts.append((start, cut))
        start = cut
    parts.append((start, len(samples)))
    return parts


def _post(api_key):
    def post(fields, audio):
        boundary = uuid.uuid4().hex
        body = b''.join([*(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8')
                           for k, v in fields.items()),
                         f'--{boundary}\r\nContent-Disposition: form-data; name="audio_file"; filename="clip.wav"\r\n'
                         'Content-Type: audio/wav\r\n\r\n'.encode('utf-8') + audio + b'\r\n',
                         f'--{boundary}--\r\n'.encode('utf-8')])
        request = urllib.request.Request(URL, data=body, method='POST', headers={
            'X-API-Key-ID': api_key, 'Content-Type': 'multipart/form-data; boundary=' + boundary, 'User-Agent': 'voicerx'})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            return error.code, {'error': error.read().decode('utf-8', 'replace')[:300]}
        except (urllib.error.URLError, TimeoutError) as error:
            return 503, {'error': f'could not reach Prisma: {error}'}
    return post


def transcribe_segment(samples, language, texts, post):
    """One piece of at most 29 seconds, sent with the text before it; '' when it holds no speech."""
    fields = {'model': 'prisma-v3.0', 'language_code': LANGUAGE_CODES.get(language, 'hi-IN,en-IN'), 'format': 'codemix'}
    previous = ' '.join(texts)[-PREVIOUS_TEXT:]
    if previous:
        fields['previous_text'] = previous
    status, reply = post(fields, wav_bytes(samples))
    if status != 200:
        raise PrismaError(f'Prisma answered {status}: {str(reply.get("error", ""))[:200]}',
                          transient=status == 429 or status >= 500)
    if reply.get('truncated'):
        raise PrismaError('Prisma truncated a segment; the recording was not transcribed in full.')
    return reply.get('transcript', '').strip()


def transcript_meta(language, segment_count, seconds, **extra):
    return {'provider': 'gnani-prisma', 'model': 'prisma-v3.0', 'format': 'codemix',
            'language_code': LANGUAGE_CODES.get(language, 'hi-IN,en-IN'), 'segments': segment_count,
            'seconds': round(seconds, 1), **extra}


def transcribe(samples, language, api_key, post=None):
    """The whole recording's transcript, and what was sent: segments, seconds, language code."""
    post = post or _post(api_key)
    texts = []
    parts = segments(samples)
    for start, end in parts:
        text = transcribe_segment(samples[start:end], language, texts, post)
        if text:
            texts.append(text)
    text = ' '.join(texts)
    if not text:
        raise PrismaError('Prisma found no speech in the recording.')
    return text, transcript_meta(language, len(parts), len(samples) / RATE)
