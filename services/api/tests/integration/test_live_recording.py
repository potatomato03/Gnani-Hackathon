"""A recording sent in pieces during the visit becomes the visit's source, and its run starts with the
transcript already made (runbook D-131). Rollback-only, synthetic records, Prisma faked."""
from uuid import uuid4

import numpy

from test_dashboard_followup import world, pytestmark
from voicerx.app import live_recordings, main
from voicerx.speech.prisma import RATE, wav_bytes


def so_far(data, seconds, of):
    return data[:44 + (len(data) - 44) * seconds // of // 2 * 2]


def test_pieces_become_the_source_and_the_run_starts_transcribed(world, monkeypatch):
    w, calls = world, []
    client, conn = w['client'], w['conn']
    monkeypatch.setattr(live_recordings, 'transaction', main.transaction)
    monkeypatch.setattr(live_recordings, 'poster', lambda: lambda fields, audio: (
        calls.append(fields) or (200, {'transcript': f'part{len(calls)}'})))
    conn.execute("update app.patients set consents = array_append(consents, 'recording') where id = %s", (w['patient'],))
    eid = 'enc-live-' + uuid4().hex[:10]
    conn.execute("insert into app.encounters(id,organisation_id,patient_id,clinician_id,visit_date,state) "
                 "values(%s,%s,%s,%s,current_date,'open')", (eid, w['org'], w['patient'], w['doc']))
    samples = numpy.full(70 * RATE, 0.5, dtype=numpy.float32)
    for pause in (24, 49):
        samples[pause * RATE:int((pause + 0.6) * RATE)] = 0
    whole = wav_bytes(samples)
    pieces = [so_far(whole, 40, 70), so_far(whole, 65, 70), whole]
    pieces = [b[len(a):] for a, b in zip([b''] + pieces, pieces)]

    start = {'media_type': 'audio/wav', 'language': 'hinglish'}
    assert client.post(f'/api/v1/encounters/{eid}/live-recordings', json=start).status_code == 422
    begun = client.post(f'/api/v1/encounters/{eid}/live-recordings', json={**start, 'recording_consent': True})
    assert begun.status_code == 201, begun.text
    lid = begun.json()['id']
    put = lambda part, data, final=False: client.put(f'/api/v1/live-recordings/{lid}/parts/{part}' + ('?final=true' if final else ''),
                                                     content=data, headers={'Content-Type': 'application/octet-stream'})

    first = put(0, pieces[0])
    assert first.status_code == 200, first.text
    assert first.json()['segments'] == 1 and 24 <= first.json()['transcribed_s'] <= 24.6
    assert put(0, pieces[0]).json() == first.json()  # a repeat is answered, not added twice
    assert put(2, pieces[2]).status_code == 409
    assert client.post(f'/api/v1/live-recordings/{lid}/complete').status_code == 409
    live_recordings.FILES.drop(lid)  # the next piece reaches a process that holds nothing yet
    assert put(1, pieces[1]).json()['segments'] == 2
    last = put(2, pieces[2], final=True).json()
    assert last['finished'] and last['transcribed_s'] == last['heard_s'] == 70.0 and last['segments'] == 3
    assert calls[2]['previous_text'] == 'part1 part2'

    done = client.post(f'/api/v1/live-recordings/{lid}/complete')
    assert done.status_code == 200, done.text
    source = done.json()
    assert source['kind'] == 'audio' and source['duration_s'] == 70.0
    assert client.post(f'/api/v1/live-recordings/{lid}/complete').json()['id'] == source['id']
    stored = conn.execute('select data from app.source_files where source_id = %s', (source['id'],)).fetchone()
    assert bytes(stored['data']) == whole  # the pieces, joined, are the recording

    run = client.post(f'/api/v1/encounters/{eid}/runs', json={'source_id': source['id'], 'source_version': source['version']})
    assert run.status_code == 202, run.text
    row = conn.execute('select transcript, transcript_meta from app.runs where id = %s', (run.json()['run_id'],)).fetchone()
    assert row['transcript'] == 'part1 part2 part3'
    assert row['transcript_meta']['live'] is True and row['transcript_meta']['segments'] == 3
    assert conn.execute('select 1 from app.live_recordings where id = %s', (lid,)).fetchone() is None
