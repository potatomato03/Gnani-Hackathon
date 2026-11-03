import sys

import pytest

from voicerx.app import knowledge


def test_a_blocked_mmh3_gets_a_stand_in_that_refuses_to_hash(monkeypatch):
    # Windows Application Control blocked mmh3's compiled file (runbook C-69); fastembed imports it only for
    # BM25 sparse embeddings, which the app never uses.
    monkeypatch.setitem(sys.modules, 'mmh3', None)
    knowledge.stand_in_for_mmh3()
    import mmh3
    with pytest.raises(RuntimeError, match='not used'):
        mmh3.hash('x')


def test_a_working_mmh3_is_left_alone(monkeypatch):
    real = type(sys)('mmh3')
    monkeypatch.setitem(sys.modules, 'mmh3', real)
    knowledge.stand_in_for_mmh3()
    assert sys.modules['mmh3'] is real
