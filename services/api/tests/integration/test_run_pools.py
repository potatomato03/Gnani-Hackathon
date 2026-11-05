"""Runs are processed only by the deployment that created them (runbook D-132). Rollback-only, synthetic records."""
from dataclasses import replace
from uuid import uuid4

from test_dashboard_followup import world, pytestmark
from voicerx.app import main
from voicerx.app.worker import claim_run

# How workers claimed runs before pools; a worker on another computer may still run this.
LEGACY_CLAIM = '''select id from app.runs where id = %s and ((state in ('queued', 'retry_wait') and not_before <= now())
                  or (state = 'running' and lease_until < now()))'''


def test_a_run_is_taken_only_by_its_own_pool_and_never_by_older_workers(world, monkeypatch):
    w = world
    client, conn = w['client'], w['conn']
    pool = 'test-' + uuid4().hex[:8]
    monkeypatch.setitem(main.state, 'settings', replace(main.state['settings'], worker_pool=pool))
    eid = 'enc-pool-' + uuid4().hex[:10]
    conn.execute("insert into app.encounters(id,organisation_id,patient_id,clinician_id,visit_date,state) "
                 "values(%s,%s,%s,%s,current_date,'open')", (eid, w['org'], w['patient'], w['doc']))
    source = client.post(f'/api/v1/encounters/{eid}/sources', json={'kind': 'typed', 'text': 'Fever for two days.'}).json()
    run_id = client.post(f'/api/v1/encounters/{eid}/runs', json={'source_id': source['id'], 'source_version': source['version']}).json()['run_id']

    row = conn.execute('select pool, due_at, not_before, lease_until from app.runs where id = %s', (run_id,)).fetchone()
    assert row['pool'] == pool and row['due_at'] is not None
    assert conn.execute(LEGACY_CLAIM, (run_id,)).fetchone() is None
    assert claim_run(conn, 'some-other-computer') is None or conn.execute(
        'select pool from app.runs where id = %s', (run_id,)).fetchone()['pool'] == pool
    claimed = claim_run(conn, pool)
    assert claimed['id'] == run_id and claimed['state'] == 'running' and claimed['pool_lease_until'] is not None
    # Even while running, and after its lease runs out, an older worker still cannot see it.
    conn.execute("update app.runs set pool_lease_until = now() - interval '1 minute' where id = %s", (run_id,))
    assert conn.execute(LEGACY_CLAIM, (run_id,)).fetchone() is None
    assert claim_run(conn, pool)['id'] == run_id  # its own pool takes back a run whose worker stopped

    # A run failed elsewhere joins the pool of the deployment the doctor retries from.
    conn.execute("update app.runs set state = 'failed', pool = null, not_before = now(), lease_until = null where id = %s",
                 (run_id,))
    retried = client.post(f'/api/v1/runs/{run_id}/retry')
    assert retried.status_code == 202, retried.text
    row = conn.execute('select state, pool from app.runs where id = %s', (run_id,)).fetchone()
    assert row == {'state': 'queued', 'pool': pool} and conn.execute(LEGACY_CLAIM, (run_id,)).fetchone() is None
