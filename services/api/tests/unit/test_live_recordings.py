"""Transcribing a recording while it is still arriving (runbook D-131)."""
import numpy

from voicerx.app.live_recordings import advance
from voicerx.speech.prisma import RATE, transcribe, wav_bytes


def speech_with_pauses(seconds, pauses):
    samples = numpy.full(int(seconds * RATE), 0.5, dtype=numpy.float32)
    for pause in pauses:
        samples[int(pause * RATE):int((pause + 0.6) * RATE)] = 0
    return samples


def so_far(data, seconds, of):
    """The file as it stood after `seconds`, cut on a whole sample as a recorder's piece would be."""
    return data[:44 + (len(data) - 44) * seconds // of // 2 * 2]


class Prisma:
    """Answers each segment with its length, and remembers what text went before it."""
    def __init__(self, fail_on=()):
        self.calls, self.fail_on = [], set(fail_on)

    def __call__(self, fields, audio):
        self.calls.append(fields)
        if len(self.calls) in self.fail_on:
            return 503, {'error': 'busy'}
        return 200, {'transcript': f'part{len(self.calls)}'}


def test_pieces_are_transcribed_as_they_arrive_and_match_the_whole_recording():
    samples = speech_with_pauses(70, pauses=[24, 49])
    whole = wav_bytes(samples)
    live, done, texts = Prisma(), 0, []
    # The file so far after 40 s: only the first segment is finished.
    done, texts, sent, total, error = advance(so_far(whole, 40, 70), 'hinglish', done, texts, False, live)
    assert (sent, error, len(live.calls)) == (1, None, 1) and 24 <= done / RATE <= 24.6
    # After 65 s the second is finished too; the rest waits for the end.
    done, texts, sent, total, error = advance(so_far(whole, 65, 70), 'hinglish', done, texts, False, live)
    assert sent == 1 and 49 <= done / RATE <= 49.6
    done, texts, sent, total, error = advance(whole, 'hinglish', done, texts, True, live)
    assert (sent, done, total) == (1, len(samples), len(samples)) and texts == ['part1', 'part2', 'part3']
    assert live.calls[2]['previous_text'] == 'part1 part2'
    # The same cuts and the same context as transcribing the whole file at once.
    after = Prisma()
    text, meta = transcribe(samples, 'hinglish', 'key', post=after)
    assert text == ' '.join(texts) and after.calls == live.calls and meta['segments'] == 3


def test_a_busy_prisma_leaves_the_place_kept_for_the_next_piece():
    whole = wav_bytes(speech_with_pauses(70, pauses=[24, 49]))
    prisma = Prisma(fail_on={2})
    done, texts, sent, _, error = advance(whole, 'hinglish', 0, [], True, prisma)
    assert error and 'busy' in error and sent == 1 and texts == ['part1'] and 24 <= done / RATE <= 24.6
    done, texts, sent, _, error = advance(whole, 'hinglish', done, texts, True, prisma)
    assert error is None and texts == ['part1', 'part3', 'part4'] and sent == 2


def test_nothing_is_sent_until_a_segment_is_finished_and_settled():
    whole = wav_bytes(speech_with_pauses(20, pauses=[]))
    prisma = Prisma()
    assert advance(whole, 'hinglish', 0, [], False, prisma)[:3] == (0, [], 0) and not prisma.calls


def test_a_tail_too_short_to_hold_speech_is_not_sent():
    samples = speech_with_pauses(30, pauses=[])
    prisma = Prisma()
    done, texts, sent, total, error = advance(wav_bytes(samples), 'hinglish', len(samples) - RATE // 10, ['earlier'], True,
                                              prisma)
    assert (done, texts, sent, error) == (len(samples), ['earlier'], 0, None) and not prisma.calls


def test_a_piece_that_cannot_be_read_yet_is_not_an_error_that_moves_anything():
    assert advance(b'not audio', 'hinglish', 0, [], False, Prisma())[:4] == (0, [], 0, None)


def test_the_recommended_medicines_are_remade_at_most_once_a_minute_and_one_at_a_time():
    import threading
    from voicerx.app.live_recordings import Refresher
    now, made, release = [1000.0], [], threading.Event()

    def make(*args):
        made.append(args)
        release.wait(2)
    refresher = Refresher(make, clock=lambda: now[0])
    assert refresher.offer('live-1', 'enc-1', 'org', 'fever') is True
    assert refresher.offer('live-1', 'enc-1', 'org', 'fever, cough') is False   # one already running
    release.set()
    for _ in range(100):
        if 'live-1' not in refresher.running:
            break
        threading.Event().wait(0.01)
    now[0] += 30
    assert refresher.offer('live-1', 'enc-1', 'org', 'fever, cough') is False   # not a minute yet
    now[0] += 31
    assert refresher.offer('live-1', 'enc-1', 'org', 'fever, cough, sore throat') is True
    assert refresher.offer('live-2', 'enc-2', 'org', 'rash') is True            # each recording on its own
    assert Refresher(None).offer('live-3', 'enc-3', 'org', 'x') is False         # nothing to make it with
