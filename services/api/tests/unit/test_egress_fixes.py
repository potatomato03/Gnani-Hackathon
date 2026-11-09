"""Keep Supabase egress inside the free allowance (runbook D-141)."""
from contextlib import contextmanager
from types import SimpleNamespace

from voicerx.app import followup, main


class FakeConn:
    def execute(self, sql, params=()):
        return SimpleNamespace(fetchone=lambda: None, fetchall=lambda: [])


def test_due_check_ins_are_looked_for_once_a_minute(monkeypatch, tmp_path):
    from voicerx.agent.memory import LocalMemoryStore
    service = followup.FollowupService(SimpleNamespace(artifacts_dir=tmp_path, database_url=''), channel=None,
                                       speech=None, nlu=None, reader=None, memory=LocalMemoryStore(tmp_path / 'memory'))
    looks = []

    @contextmanager
    def transaction():
        looks.append(1)
        yield FakeConn()
    monkeypatch.setattr(followup, 'transaction', transaction)
    clock = [1000.0]
    monkeypatch.setattr(followup.time, 'monotonic', lambda: clock[0])
    service.scheduled()
    service.scheduled()
    clock[0] += followup.SCHEDULE_EVERY - 1
    service.scheduled()
    assert len(looks) == 1
    clock[0] += 1
    service.scheduled()
    assert len(looks) == 2


def test_warm_up_loads_the_product_index_first_and_only_when_asked(monkeypatch):
    calls = []
    monkeypatch.setattr(main.knowledge, 'warm_up', lambda: calls.append('model'))
    monkeypatch.setattr(main, 'shared_index', lambda conn, products: calls.append('products'))

    @contextmanager
    def transaction():
        yield FakeConn()
    monkeypatch.setattr(main, 'transaction', transaction)
    main.warm_up(products=False)
    assert calls == ['model']
    main.warm_up()
    assert calls == ['model', 'products', 'model']


class CountConn:
    """Answers the row count, and the full product query when asked."""
    def __init__(self, count, rows=()):
        self.count, self.rows, self.queries = count, list(rows), []

    def execute(self, sql, params=()):
        self.queries.append(sql)
        if 'count(*)' in sql:
            return SimpleNamespace(fetchone=lambda: {'n': self.count})
        return SimpleNamespace(fetchall=lambda: self.rows)


ROWS = [[1, 'Dolo 650 Tablet', 'Paracetamol (650mg)', 'Micro Labs', 0.9],
        [2, 'Pan 40 Tablet', 'Pantoprazole (40mg)', None, 0.8]]


def write_snapshot(path, rows, count=None):
    import gzip, json
    path.write_bytes(gzip.compress(json.dumps({'count': len(rows) if count is None else count, 'rows': rows}).encode()))


def test_products_come_from_the_shipped_snapshot_without_reading_the_table(monkeypatch, tmp_path):
    from voicerx.app import suggest
    snapshot = tmp_path / 'indian_products.json.gz'
    write_snapshot(snapshot, ROWS)
    monkeypatch.setattr(suggest, 'PRODUCTS_SNAPSHOT', snapshot)
    conn = CountConn(2)
    rows = suggest.indian_rows(conn)
    assert rows[0] == {'id': 1, 'name': 'Dolo 650 Tablet', 'composition': 'Paracetamol (650mg)',
                       'manufacturer': 'Micro Labs', 'popularity': 0.9}
    assert len(rows) == 2 and len(conn.queries) == 1 and 'count(*)' in conn.queries[0]


def test_a_stale_missing_or_broken_snapshot_falls_back_to_postgres(monkeypatch, tmp_path):
    from voicerx.app import suggest
    table = [{'id': 1, 'name': 'Dolo 650 Tablet', 'composition': 'Paracetamol (650mg)', 'manufacturer': 'Micro Labs',
              'popularity': 0.9}]
    snapshot = tmp_path / 'indian_products.json.gz'
    monkeypatch.setattr(suggest, 'PRODUCTS_SNAPSHOT', snapshot)
    assert suggest.indian_rows(CountConn(1, table)) == table          # missing
    write_snapshot(snapshot, ROWS)
    assert suggest.indian_rows(CountConn(1, table)) == table          # stale: table has 1, snapshot 2
    snapshot.write_bytes(b'not gzip')
    assert suggest.indian_rows(CountConn(2, table)) == table          # unreadable
