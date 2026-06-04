"""Embedding 100ms batch window + optional HTTP batch API (docs/10 §Embedding)."""

from __future__ import annotations

import asyncio
import hashlib
import logging

import httpx

from agent_factory.config import Settings, get_settings
from agent_factory.infra.model_queue import (
    acquire_embedding_queue_slot,
    acquire_rerank_queue_slot,
)
from agent_factory.infra.redis import get_redis

logger = logging.getLogger(__name__)

_broker: EmbeddingBatchBroker | None = None


def get_embedding_broker(settings: Settings | None = None) -> EmbeddingBatchBroker:
    """Process-wide coalescer (single asyncio loop)."""
    global _broker
    if _broker is None:
        _broker = EmbeddingBatchBroker(settings or get_settings())
    return _broker


def reset_embedding_broker_for_tests() -> None:
    """Test helper."""
    global _broker
    _broker = None


def _local_hash_embeddings(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for t in texts:
        h = hashlib.sha256(t.encode("utf-8")).digest()
        out.append([float(b) / 255.0 for b in h[:32]])
    return out


class EmbeddingBatchBroker:
    """Coalesce ``embed_text`` calls over ``EMBEDDING_BATCH_WINDOW_MS``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._pending: list[tuple[str, asyncio.Future[list[float]]]] = []
        self._timer: asyncio.Task[None] | None = None

    async def embed_text(self, text: str) -> list[float]:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[list[float]] = loop.create_future()
        async with self._lock:
            self._pending.append((text, fut))
            if self._timer is None or self._timer.done():
                self._timer = asyncio.create_task(self._schedule_flush())
        return await fut

    async def _schedule_flush(self) -> None:
        try:
            delay = self._settings.EMBEDDING_BATCH_WINDOW_MS / 1000.0
            await asyncio.sleep(delay)
            await self._flush()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("embedding batch flush task failed")

    async def _flush(self) -> None:
        async with self._lock:
            batch = self._pending[:]
            self._pending.clear()
            self._timer = None
        if not batch:
            return
        futs = [f for _, f in batch]
        texts_all = [t for t, _ in batch]
        max_n = self._settings.EMBEDDING_BATCH_MAX_ITEMS
        try:
            out_vecs: list[list[float]] = []
            i = 0
            while i < len(texts_all):
                chunk = texts_all[i : i + max_n]
                out_vecs.extend(await self._invoke_batch(chunk))
                i += max_n
            if len(out_vecs) != len(futs):
                raise RuntimeError("embedding batch size mismatch")
            for f, v in zip(futs, out_vecs, strict=True):
                if not f.done():
                    f.set_result(v)
        except Exception as exc:
            for f in futs:
                if not f.done():
                    f.set_exception(exc)
        async with self._lock:
            if self._pending and (
                self._timer is None or self._timer.done()
            ):
                self._timer = asyncio.create_task(self._schedule_flush())

    async def _invoke_batch(self, texts: list[str]) -> list[list[float]]:
        ep = (self._settings.EMBEDDING_ENDPOINT or "").strip().rstrip("/")
        if not ep:
            return _local_hash_embeddings(texts)
        url = f"{ep}/embeddings"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        key = (self._settings.EMBEDDING_API_KEY or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": self._settings.EMBEDDING_MODEL,
            "input": texts,
        }
        redis = get_redis()
        async with acquire_embedding_queue_slot(redis, self._settings):
            async with acquire_rerank_queue_slot(redis, self._settings):
                async with httpx.AsyncClient(
                    timeout=self._settings.EMBEDDING_HTTP_TIMEOUT_SECONDS,
                ) as client:
                    r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        body = r.json()
        data = body.get("data") or []
        out: list[list[float]] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise RuntimeError(f"bad embedding item at {i}")
            emb = item.get("embedding")
            if not isinstance(emb, list):
                raise RuntimeError(f"bad embedding at {i}")
            out.append([float(x) for x in emb])
        if len(out) != len(texts):
            raise RuntimeError("embeddings response length mismatch")
        return out
