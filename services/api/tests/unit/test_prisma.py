import io
import wave

import numpy
import pytest

from voicerx.speech.prisma import (LANGUAGE_CODES, RATE, PrismaError, decode_audio, segments, transcribe, wav_bytes)


def tone_with_gaps(seconds, gaps):
    """A loud signal with silent stretches at the given seconds."""
    samples = numpy.full(int(seconds * RATE), 0.5, dtype=numpy.float32)
    for gap in gaps:
        samples[int(gap * RATE):int((gap + 0.6) * RATE)] = 0
    return samples


def test_short_audio_is_one_segment():
    assert segments(numpy.zeros(10 * RATE, dtype=numpy.float32)) == [(0, 10 * RATE)]


def test_long_audio_splits_in_its_quiet_stretches_and_loses_nothing():
    samples = tone_with_gaps(70, gaps=[24, 49])
    parts = segments(samples)
    assert parts[0][0] == 0 and parts[-1][1] == len(samples)
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:]))
    assert all((end - start) / RATE <= 29 for start, end in parts)
    assert 24 <= parts[0][1] / RATE <= 24.6 and 49 <= parts[1][1] / RATE <= 49.6


def test_audio_with_no_pause_is_still_cut_within_the_limit():
    parts = segments(numpy.full(65 * RATE, 0.5, dtype=numpy.float32))
    assert all((end - start) / RATE <= 29 for start, end in parts) and parts[-1][1] == 65 * RATE


def test_wav_round_trip_keeps_16_khz_mono():
    data = wav_bytes(numpy.zeros(RATE, dtype=numpy.float32))
    with wave.open(io.BytesIO(data)) as reader:
        assert (reader.getframerate(), reader.getnchannels(), reader.getnframes()) == (RATE, 1, RATE)
    assert len(decode_audio(data)) == RATE


def test_each_segment_is_sent_with_the_text_before_it():
    calls = []

    def post(fields, audio):
        calls.append(fields)
        return 200, {'transcript': f'part {len(calls)}'}

    text, meta = transcribe(tone_with_gaps(50, gaps=[24]), 'hinglish', 'key', post)
    assert text == 'part 1 part 2' and meta['segments'] == 2
    assert calls[0]['language_code'] == LANGUAGE_CODES['hinglish'] == 'hi-IN,en-IN'
    assert calls[0]['model'] == 'prisma-v3.0' and calls[0]['format'] == 'codemix' and 'keyterms' not in calls[0]
    assert 'previous_text' not in calls[0] and calls[1]['previous_text'] == 'part 1'


def test_a_truncated_reply_is_an_error_never_a_shorter_transcript():
    with pytest.raises(PrismaError, match='truncated'):
        transcribe(numpy.zeros(5 * RATE, dtype=numpy.float32), 'english', 'key',
                   lambda f, a: (200, {'transcript': 'cut', 'truncated': True}))


def test_rate_limits_and_server_errors_are_retryable_but_bad_requests_are_not():
    with pytest.raises(PrismaError) as busy:
        transcribe(numpy.zeros(RATE, dtype=numpy.float32), 'english', 'key', lambda f, a: (429, {'error': 'slow down'}))
    assert busy.value.transient
    with pytest.raises(PrismaError) as bad:
        transcribe(numpy.zeros(RATE, dtype=numpy.float32), 'english', 'key', lambda f, a: (400, {'error': 'bad'}))
    assert not bad.value.transient


def test_silence_is_refused_rather_than_making_an_empty_note():
    with pytest.raises(PrismaError, match='no speech'):
        transcribe(numpy.zeros(3 * RATE, dtype=numpy.float32), 'english', 'key', lambda f, a: (200, {'transcript': ''}))
