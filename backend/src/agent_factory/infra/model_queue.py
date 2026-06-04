"""Model queue: ZSET priority, inflight cap, fairness, aging, eviction (docs/10)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from agent_factory.config.settings import Settings
from agent_factory.infra.model_client import ModelClientError

logger = logging.getLogger(__name__)

QUEUE_CLASSES = frozenset(
    {"privileged", "interactive", "document", "batch"},
)

FAIR_CREDITS_KEY = "model:fair:credits"

# KEYS: z, inf, fairk, docz, batz — ARGV: ticket, cap, cls
_LUA_CLAIM_HEAD_FAIR = """
local z = KEYS[1]
local infk = KEYS[2]
local fairk = KEYS[3]
local docz = KEYS[4]
local batz = KEYS[5]
local ticket = ARGV[1]
local cap = tonumber(ARGV[2])
local cls = ARGV[3]
local docn = redis.call('ZCARD', docz)
local batn = redis.call('ZCARD', batz)
if (docn + batn) > 0 then
  if cls == 'interactive' or cls == 'privileged' then
    local cr = tonumber(redis.call('GET', fairk) or '5')
    if cr <= 0 then
      return 2
    end
  end
end
local head = redis.call('ZRANGE', z, 0, 0)
if (not head) or (#head == 0) then
  return 0
end
if head[1] ~= ticket then
  return 0
end
local cur = tonumber(redis.call('GET', infk) or '0')
if cur >= cap then
  return 0
end
redis.call('ZREM', z, ticket)
redis.call('INCR', infk)
if cls == 'interactive' or cls == 'privileged' then
  local cr = tonumber(redis.call('GET', fairk) or '5')
  if cr > 0 then
    redis.call('DECR', fairk)
  end
elseif cls == 'document' or cls == 'batch' then
  redis.call('SET', fairk, '5')
end
return 1
"""

_LUA_TRY_INCR = """
local k = KEYS[1]
local cap = tonumber(ARGV[1])
local n = redis.call('INCR', k)
if n <= cap then
  return 1
end
redis.call('DECR', k)
return 0
"""


class ModelQueuePolicyError(ModelClientError):
    """Queue / backpressure (maps to HTTP 429 + Retry-After when applicable)."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int = 429,
        retry_after: int = 5,
    ) -> None:
        super().__init__(message)
        self.http_status = int(http_status)
        self.retry_after = int(retry_after)


def zset_enqueue_score(queue_priority: int, ts: float | None = None) -> float:
    """Smaller score = higher priority; FIFO within same priority (docs/10)."""
    t = ts if ts is not None else time.time()
    ts_ms = float(t) * 1000.0
    pri = max(1, min(int(queue_priority), 20))
    return float(-pri) * 1.0e15 + ts_ms


def _zqueue_key(concurrency_class: str) -> str:
    return f"model:zqueue:{concurrency_class}"


def _inflight_key(concurrency_class: str) -> str:
    return f"model:inflight:{concurrency_class}"


def _nack_key(ticket: str) -> str:
    return f"model:q:nack:{ticket}"


def _enq_ts_key(ticket: str) -> str:
    return f"model:q:enqts:{ticket}"


def _cap_for_class(settings: Settings, concurrency_class: str) -> int:
    m = {
        "privileged": settings.MODEL_QUEUE_CAP_PRIVILEGED,
        "interactive": settings.MODEL_QUEUE_CAP_INTERACTIVE,
        "document": settings.MODEL_QUEUE_CAP_DOCUMENT,
        "batch": settings.MODEL_QUEUE_CAP_BATCH,
    }
    return int(m.get(concurrency_class, settings.MODEL_QUEUE_CAP_INTERACTIVE))


def _max_zqueue_for_class(settings: Settings, concurrency_class: str) -> int:
    m = {
        "privileged": settings.MODEL_QUEUE_MAX_ZQUEUE_PRIVILEGED,
        "interactive": settings.MODEL_QUEUE_MAX_ZQUEUE_INTERACTIVE,
        "document": settings.MODEL_QUEUE_MAX_ZQUEUE_DOCUMENT,
        "batch": settings.MODEL_QUEUE_MAX_ZQUEUE_BATCH,
    }
    return int(m.get(concurrency_class, settings.MODEL_QUEUE_MAX_ZQUEUE_INTERACTIVE))


async def _set_nack(redis: Redis, ticket: str, ttl: int = 120) -> None:
    await redis.set(_nack_key(ticket), "1", ex=ttl)


async def _trim_batch_queue_drop_oldest(
    redis: Redis,
    zkey: str,
    maxlen: int,
) -> None:
    """batch: drop longest-waiting (ZPOPMIN) when at capacity (docs/10)."""
    while int(await redis.zcard(zkey)) >= maxlen:
        popped = await redis.zpopmin(zkey, 1)
        if not popped:
            break
        old = popped[0][0]
        await _set_nack(redis, str(old))


async def _evict_interactive_tail_for_privileged(
    redis: Redis,
    settings: Settings,
) -> bool:
    """ZPOPMAX interactive = lowest-priority tail; nack (docs/10)."""
    ikey = _zqueue_key("interactive")
    popped = await redis.zpopmax(ikey, 1)
    if not popped:
        return False
    old = popped[0][0]
    await _set_nack(redis, str(old))
    logger.warning(
        "Evicted interactive queue tail %s for privileged admission",
        old,
    )
    return True


async def _make_room_privileged(
    redis: Redis,
    settings: Settings,
    zkey: str,
    maxlen: int,
) -> None:
    while int(await redis.zcard(zkey)) >= maxlen:
        if not await _evict_interactive_tail_for_privileged(redis, settings):
            raise ModelQueuePolicyError(
                "privileged model queue full and no interactive tail to evict",
                http_status=503,
                retry_after=30,
            )


async def preflight_model_queue_or_raise(
    redis: Redis,
    settings: Settings,
    concurrency_class: str,
) -> None:
    """Soft ZCARD limits → HTTP 429 semantics before SSE (docs/10)."""
    if not settings.MODEL_QUEUE_ENABLED:
        return
    cls = concurrency_class if concurrency_class in QUEUE_CLASSES else "interactive"
    zkey = _zqueue_key(cls)
    n = int(await redis.zcard(zkey))
    if cls == "interactive" and n >= settings.MODEL_QUEUE_SOFT_ZCARD_INTERACTIVE:
        raise ModelQueuePolicyError(
            "interactive model queue busy",
            retry_after=settings.MODEL_QUEUE_RETRY_AFTER_INTERACTIVE,
        )
    if cls == "document" and n >= settings.MODEL_QUEUE_SOFT_ZCARD_DOCUMENT:
        raise ModelQueuePolicyError(
            "document model queue busy",
            retry_after=settings.MODEL_QUEUE_RETRY_AFTER_DOCUMENT,
        )
    if cls == "privileged" and n >= settings.MODEL_QUEUE_SOFT_ZCARD_PRIVILEGED:
        raise ModelQueuePolicyError(
            "privileged model queue busy",
            retry_after=settings.MODEL_QUEUE_RETRY_AFTER_PRIVILEGED,
        )


def _aging_zincrby(
    settings: Settings,
    waited_s: float,
    aging_stage: int,
) -> tuple[float, int]:
    """Return (score_delta, new_stage) for priority aging (docs/10)."""
    d1 = float(settings.MODEL_QUEUE_AGING_DELTA_1)
    d2 = float(settings.MODEL_QUEUE_AGING_DELTA_2)
    df = float(settings.MODEL_QUEUE_AGING_FORCE_DELTA)
    s1 = float(settings.MODEL_QUEUE_AGING_SEC_1)
    s2 = float(settings.MODEL_QUEUE_AGING_SEC_2)
    s3 = float(settings.MODEL_QUEUE_AGING_SEC_3)
    if waited_s >= s3 and aging_stage < 3:
        return -df, 3
    if waited_s >= s2 and aging_stage < 2:
        return -d2, 2
    if waited_s >= s1 and aging_stage < 1:
        return -d1, 1
    return 0.0, aging_stage


@asynccontextmanager
async def acquire_model_queue_slot(
    redis: Redis,
    settings: Settings,
    concurrency_class: str,
    *,
    queue_priority: int = 5,
) -> AsyncIterator[None]:
    """Enqueue ZSET, wait head+inflight; aging, fairness, eviction (docs/10)."""
    if not settings.MODEL_QUEUE_ENABLED:
        yield
        return
    cls = concurrency_class if concurrency_class in QUEUE_CLASSES else "interactive"
    cap = _cap_for_class(settings, cls)
    if cap <= 0:
        yield
        return
    zkey = _zqueue_key(cls)
    ifk = _inflight_key(cls)
    ticket = uuid.uuid4().hex
    score = zset_enqueue_score(queue_priority)
    maxlen = _max_zqueue_for_class(settings, cls)
    acquired = False
    deadline = time.monotonic() + (settings.MODEL_QUEUE_ACQUIRE_TIMEOUT_MS / 1000.0)
    enq_wall = time.time()
    aging_stage = 0
    doc_z = _zqueue_key("document")
    bat_z = _zqueue_key("batch")
    try:
        if cls == "batch":
            await _trim_batch_queue_drop_oldest(redis, zkey, maxlen)
        elif cls == "privileged":
            await _make_room_privileged(redis, settings, zkey, maxlen)
        else:
            nwaiting = int(await redis.zcard(zkey))
            if nwaiting >= maxlen:
                raise ModelQueuePolicyError(
                    f"model zqueue '{cls}' full (max={maxlen})",
                    retry_after=settings.MODEL_QUEUE_RETRY_AFTER_INTERACTIVE,
                )
        await redis.zadd(zkey, {ticket: score})
        ttl = int(settings.MODEL_QUEUE_ACQUIRE_TIMEOUT_MS / 1000) + 180
        await redis.set(_enq_ts_key(ticket), str(enq_wall), ex=ttl)
        while time.monotonic() < deadline:
            if await redis.get(_nack_key(ticket)):
                raise ModelQueuePolicyError(
                    "displaced from model queue",
                    retry_after=settings.MODEL_QUEUE_RETRY_AFTER_INTERACTIVE,
                )
            raw_ts = await redis.get(_enq_ts_key(ticket))
            base = float(raw_ts) if raw_ts is not None else enq_wall
            waited = time.time() - base
            dz, aging_stage = _aging_zincrby(settings, waited, aging_stage)
            if dz != 0.0:
                await redis.zincrby(zkey, dz, ticket)
            raw = await redis.eval(
                _LUA_CLAIM_HEAD_FAIR,
                5,
                zkey,
                ifk,
                FAIR_CREDITS_KEY,
                doc_z,
                bat_z,
                ticket,
                str(cap),
                cls,
            )
            code = int(raw) if raw is not None else 0
            if code == 1:
                acquired = True
                break
            if code == 2:
                await asyncio.sleep(settings.MODEL_QUEUE_POLL_MS / 1000.0)
                continue
            await asyncio.sleep(settings.MODEL_QUEUE_POLL_MS / 1000.0)
        if not acquired:
            raise ModelQueuePolicyError(
                f"model zqueue '{cls}' wait timeout",
                retry_after=settings.MODEL_QUEUE_RETRY_AFTER_INTERACTIVE,
            )
        yield
    finally:
        try:
            await redis.delete(_enq_ts_key(ticket))
        except Exception:
            logger.exception("enqueue ts key delete failed")
        if acquired:
            try:
                n = await redis.decr(ifk)
                if int(n) < 0:
                    await redis.set(ifk, "0")
            except Exception:
                logger.exception("model inflight decr failed key=%s", ifk)
        else:
            try:
                await redis.zrem(zkey, ticket)
            except Exception:
                logger.exception("model zqueue zrem cleanup failed")


@asynccontextmanager
async def acquire_embedding_queue_slot(
    redis: Redis,
    settings: Settings,
) -> AsyncIterator[None]:
    """Inflight cap for embedding HTTP batches (docs/10 §Embedding)."""
    if not settings.MODEL_QUEUE_ENABLED:
        yield
        return
    cap = int(settings.MODEL_QUEUE_CAP_EMBEDDING)
    if cap <= 0:
        yield
        return
    key = "model:inflight:embedding"
    deadline = time.monotonic() + (settings.MODEL_QUEUE_ACQUIRE_TIMEOUT_MS / 1000.0)
    acquired = False
    while time.monotonic() < deadline:
        raw = await redis.eval(_LUA_TRY_INCR, 1, key, str(cap))
        ok = int(raw) if raw is not None else 0
        if ok == 1:
            acquired = True
            break
        await asyncio.sleep(settings.MODEL_QUEUE_POLL_MS / 1000.0)
    if not acquired:
        raise ModelClientError("embedding model queue saturated")
    try:
        yield
    finally:
        if acquired:
            try:
                n = await redis.decr(key)
                if int(n) < 0:
                    await redis.set(key, "0")
            except Exception:
                logger.exception("embedding queue decr failed")


@asynccontextmanager
async def acquire_rerank_queue_slot(
    redis: Redis,
    settings: Settings,
) -> AsyncIterator[None]:
    """Separate inflight bucket so rerank/embed bursts do not starve chat."""
    if not settings.MODEL_QUEUE_ENABLED:
        yield
        return
    cap = int(settings.MODEL_QUEUE_CAP_RERANK)
    if cap <= 0:
        yield
        return
    key = "model:inflight:rerank"
    deadline = time.monotonic() + (settings.MODEL_QUEUE_ACQUIRE_TIMEOUT_MS / 1000.0)
    acquired = False
    while time.monotonic() < deadline:
        raw = await redis.eval(_LUA_TRY_INCR, 1, key, str(cap))
        ok = int(raw) if raw is not None else 0
        if ok == 1:
            acquired = True
            break
        await asyncio.sleep(settings.MODEL_QUEUE_POLL_MS / 1000.0)
    if not acquired:
        raise ModelClientError("rerank model queue saturated")
    try:
        yield
    finally:
        if acquired:
            try:
                n = await redis.decr(key)
                if int(n) < 0:
                    await redis.set(key, "0")
            except Exception:
                logger.exception("rerank queue decr failed")
