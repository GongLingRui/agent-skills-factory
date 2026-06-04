"""ZSET score ordering + priority aging stages (docs/10)."""

from agent_factory.config.settings import Settings
from agent_factory.infra.model_queue import _aging_zincrby, zset_enqueue_score


def test_higher_priority_smaller_score():
    a = zset_enqueue_score(10, ts=1000.0)
    b = zset_enqueue_score(5, ts=1000.0)
    assert a < b


def test_same_priority_fifo_by_time():
    t0 = 2000.0
    t1 = 2000.001
    a = zset_enqueue_score(5, ts=t0)
    b = zset_enqueue_score(5, ts=t1)
    assert a < b


def test_aging_zincrby_stages():
    s = Settings.model_construct(
        MODEL_QUEUE_AGING_SEC_1=30.0,
        MODEL_QUEUE_AGING_SEC_2=60.0,
        MODEL_QUEUE_AGING_SEC_3=120.0,
        MODEL_QUEUE_AGING_DELTA_1=1e14,
        MODEL_QUEUE_AGING_DELTA_2=2e14,
        MODEL_QUEUE_AGING_FORCE_DELTA=3e15,
    )
    d, st = _aging_zincrby(s, 29.0, 0)
    assert (d, st) == (0.0, 0)
    d, st = _aging_zincrby(s, 30.0, 0)
    assert st == 1 and d == -1e14
    d, st = _aging_zincrby(s, 60.0, 1)
    assert st == 2 and d == -2e14
    d, st = _aging_zincrby(s, 120.0, 2)
    assert st == 3 and d == -3e15
    d, st = _aging_zincrby(s, 200.0, 3)
    assert (d, st) == (0.0, 3)
