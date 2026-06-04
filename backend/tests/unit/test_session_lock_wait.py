"""Tests for bounded session chat lock waiting (FIFO fairness)."""

import asyncio

import pytest

from agent_factory.infra.session_lock import (
    LOCK_KEY_PREFIX,
    QUEUE_KEY_PREFIX,
    acquire_session_lock,
    acquire_session_lock_or_wait,
    release_session_lock,
)


class _FakeRedis:
    """Minimal async Redis subset for lock tests (Lua scripts used in prod)."""

    def __init__(self) -> None:
        self._kv: dict[str, str] = {}
        self._lists: dict[str, list[str]] = {}

    async def set(self, key: str, val: str, nx: bool = False, ex: int | None = None):
        if nx and key in self._kv:
            return False
        self._kv[key] = val
        return True

    async def delete(self, key: str) -> None:
        self._kv.pop(key, None)

    async def expire(self, key: str, sec: int) -> bool:
        return True

    async def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))

    async def lindex(self, key: str, idx: int) -> str | None:
        lst = self._lists.get(key, [])
        i = int(idx)
        if i < 0 or i >= len(lst):
            return None
        return lst[i]

    async def lpop(self, key: str) -> str | None:
        lst = self._lists.setdefault(key, [])
        if not lst:
            return None
        return lst.pop(0)

    async def lrem(self, key: str, count: int, value: str) -> int:
        lst = self._lists.setdefault(key, [])
        c = int(count)
        removed = 0
        if c > 0:
            i = 0
            while i < len(lst) and removed < c:
                if lst[i] == value:
                    lst.pop(i)
                    removed += 1
                else:
                    i += 1
        return removed

    async def eval(self, script: str, numkeys: int, *args: str) -> int:
        keys = list(args[:numkeys])
        argv = list(args[numkeys:])
        if "ACQUIRE_IF_QUEUE_EMPTY_V1" in script:
            lock_key, queue_key = keys[0], keys[1]
            ttl = int(argv[0])
            q = self._lists.setdefault(queue_key, [])
            if len(q) > 0:
                return 0
            if await self.set(lock_key, "1", nx=True, ex=ttl):
                return 1
            return 0
        if "ENQUEUE_WAITER_V1" in script:
            queue_key = keys[0]
            max_w = int(argv[0])
            token = argv[1]
            lst = self._lists.setdefault(queue_key, [])
            if len(lst) >= max_w:
                return 0
            lst.append(token)
            return 1
        raise NotImplementedError(script)


@pytest.mark.asyncio
async def test_acquire_immediate_without_contention():
    r = _FakeRedis()
    sid = "sess_a"
    ok, err = await acquire_session_lock_or_wait(
        r,
        sid,
        max_waiters=5,
        poll_interval_ms=10,
        max_wait_ms=500,
    )
    assert ok is True
    assert err is None
    assert f"{LOCK_KEY_PREFIX}{sid}" in r._kv


@pytest.mark.asyncio
async def test_busy_when_max_waiters_zero():
    r = _FakeRedis()
    sid = "sess_b"
    await acquire_session_lock(r, sid)
    ok, err = await acquire_session_lock_or_wait(
        r,
        sid,
        max_waiters=0,
        poll_interval_ms=10,
        max_wait_ms=500,
    )
    assert ok is False
    assert err == "SESSION_BUSY"


@pytest.mark.asyncio
async def test_waits_until_lock_released():
    r = _FakeRedis()
    sid = "sess_c"
    await acquire_session_lock(r, sid)

    async def waiter():
        return await acquire_session_lock_or_wait(
            r,
            sid,
            max_waiters=5,
            poll_interval_ms=5,
            max_wait_ms=2000,
        )

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0.03)
    await release_session_lock(r, sid)
    ok, err = await task
    assert ok is True
    assert err is None


@pytest.mark.asyncio
async def test_queue_full():
    r = _FakeRedis()
    sid = "sess_d"
    lock_k = f"{LOCK_KEY_PREFIX}{sid}"
    await r.set(lock_k, "1")

    async def first_waiter():
        return await acquire_session_lock_or_wait(
            r,
            sid,
            max_waiters=1,
            poll_interval_ms=5,
            max_wait_ms=800,
        )

    w1 = asyncio.create_task(first_waiter())
    await asyncio.sleep(0.02)
    ok, err = await acquire_session_lock_or_wait(
        r,
        sid,
        max_waiters=1,
        poll_interval_ms=5,
        max_wait_ms=100,
    )
    assert ok is False
    assert err == "SESSION_QUEUE_FULL"
    await r.delete(lock_k)
    ok2, err2 = await w1
    assert ok2 is True
    await release_session_lock(r, sid)


@pytest.mark.asyncio
async def test_wait_timeout():
    r = _FakeRedis()
    sid = "sess_e"
    await r.set(f"{LOCK_KEY_PREFIX}{sid}", "1")
    ok, err = await acquire_session_lock_or_wait(
        r,
        sid,
        max_waiters=3,
        poll_interval_ms=10,
        max_wait_ms=80,
    )
    assert ok is False
    assert err == "SESSION_LOCK_TIMEOUT"
    qkey = f"{QUEUE_KEY_PREFIX}{sid}"
    assert r._lists.get(qkey, []) == []


@pytest.mark.asyncio
async def test_fifo_two_waiters_acquire_order():
    """First enqueued waiter must take the lock before the second."""
    r = _FakeRedis()
    sid = "sess_fifo"
    await acquire_session_lock(r, sid)
    order: list[str] = []

    async def waiter(name: str) -> None:
        ok, err = await acquire_session_lock_or_wait(
            r,
            sid,
            max_waiters=5,
            poll_interval_ms=5,
            max_wait_ms=5000,
        )
        assert ok is True and err is None
        order.append(name)
        await release_session_lock(r, sid)

    t_first = asyncio.create_task(waiter("first"))
    await asyncio.sleep(0.02)
    t_second = asyncio.create_task(waiter("second"))
    await asyncio.sleep(0.05)
    await release_session_lock(r, sid)
    await asyncio.wait_for(asyncio.gather(t_first, t_second), timeout=5.0)
    assert order == ["first", "second"]
    qkey = f"{QUEUE_KEY_PREFIX}{sid}"
    assert r._lists.get(qkey, []) == []
