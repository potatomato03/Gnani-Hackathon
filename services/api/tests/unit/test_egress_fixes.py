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


def test_http_only_instances_do_not_preload_the_product_index(monkeypatch):
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
    assert calls == ['model', 'model', 'products']
