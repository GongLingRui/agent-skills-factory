"""Embedding 100ms batch coalescing."""

import asyncio
import time

import pytest

from agent_factory.config.settings import Settings
from agent_factory.infra.embedding_batch import (
    get_embedding_broker,
    reset_embedding_broker_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_broker():
    reset_embedding_broker_for_tests()
    yield
    reset_embedding_broker_for_tests()


@pytest.mark.asyncio
async def test_two_queries_share_one_flush_window(monkeypatch):
    s = Settings.model_construct(
        MODEL_QUEUE_ENABLED=False,
        EMBEDDING_BATCH_WINDOW_MS=40,
        EMBEDDING_ENDPOINT="",
        REDIS_URL="redis://localhost:56379/0",
    )
    monkeypatch.setattr(
        "agent_factory.infra.embedding_batch.get_settings",
        lambda: s,
    )
    b = get_embedding_broker(s)
    t0 = time.monotonic()
    v1, v2 = await asyncio.gather(b.embed_text("hello"), b.embed_text("world"))
    dt = time.monotonic() - t0
    assert dt >= 0.02
    assert len(v1) == 32 and len(v2) == 32
    assert v1 != v2
