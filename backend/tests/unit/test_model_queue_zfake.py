"""In-memory Redis subset for ZSET claim + fairness Lua (docs/10)."""

from __future__ import annotations

import pytest

from agent_factory.config.settings import Settings
from agent_factory.infra import model_queue as mq


class _FakeRedis:
    """Minimal async Redis matching ``_LUA_CLAIM_HEAD_FAIR``."""

    def __init__(self) -> None:
        self._z: dict[str, dict[str, float]] = {}
        self._kv: dict[str, str] = {}

    async def zcard(self, key: str) -> int:
        return len(self._z.get(key, {}))

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        z = self._z.setdefault(key, {})
        n = 0
        for m, s in mapping.items():
            if m not in z:
                n += 1
            z[m] = float(s)
        return n

    async def zrem(self, key: str, *members: str) -> int:
        z = self._z.get(key, {})
        c = 0
        for mem in members:
            if mem in z:
                del z[mem]
                c += 1
        return c

    async def zincrby(self, key: str, increment: float, member: str) -> float:
        z = self._z.setdefault(key, {})
        z[member] = z.get(member, 0.0) + float(increment)
        return z[member]

    async def get(self, key: str) -> str | None:
        return self._kv.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        del ex  # TTL not simulated; key lifetime is test-scoped.
        self._kv[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self._kv:
                del self._kv[k]
                n += 1
        return n

    async def incr(self, key: str) -> int:
        v = int(self._kv.get(key, "0")) + 1
        self._kv[key] = str(v)
        return v

    async def decr(self, key: str) -> int:
        v = int(self._kv.get(key, "0")) - 1
        self._kv[key] = str(v)
        return v

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> int:
        KEYS = list(keys_and_args[:numkeys])
        ARGV = list(keys_and_args[numkeys:])
        zkey, ifk, fairk, docz, batz = KEYS
        ticket, cap_s, cls = ARGV[0], int(ARGV[1]), ARGV[2]
        self._kv.setdefault(fairk, "5")
        docn = len(self._z.get(docz, {}))
        batn = len(self._z.get(batz, {}))
        cr = int(self._kv.get(fairk, "5"))
        if docn + batn > 0 and cls in ("interactive", "privileged"):
            if cr <= 0:
                return 2
        items = sorted(self._z.get(zkey, {}).items(), key=lambda x: x[1])
        if not items:
            return 0
        if items[0][0] != ticket:
            return 0
        cur = int(self._kv.get(ifk, "0"))
        if cur >= cap_s:
            return 0
        del self._z[zkey][ticket]
        await self.incr(ifk)
        if cls in ("interactive", "privileged"):
            cr2 = int(self._kv.get(fairk, "5"))
            if cr2 > 0:
                self._kv[fairk] = str(cr2 - 1)
        elif cls in ("document", "batch"):
            self._kv[fairk] = "5"
        return 1


@pytest.mark.asyncio
async def test_acquire_zqueue_happy_path():
    r = _FakeRedis()
    s = Settings.model_construct(
        MODEL_QUEUE_ENABLED=True,
        MODEL_QUEUE_CAP_INTERACTIVE=1,
        MODEL_QUEUE_MAX_ZQUEUE_INTERACTIVE=100,
        MODEL_QUEUE_ACQUIRE_TIMEOUT_MS=5000,
        MODEL_QUEUE_POLL_MS=2,
        MODEL_QUEUE_AGING_SEC_1=9999.0,
        MODEL_QUEUE_AGING_SEC_2=99999.0,
        MODEL_QUEUE_AGING_SEC_3=999999.0,
        REDIS_URL="redis://localhost:56379/0",
    )
    async with mq.acquire_model_queue_slot(
        r,
        s,
        "interactive",
        queue_priority=5,
    ):
        assert int(await r.get("model:inflight:interactive") or 0) == 1
    assert int(await r.get("model:inflight:interactive") or 0) == 0
