"""Tests for Redis model queue (requires Redis)."""

import pytest
from redis.asyncio import Redis

from agent_factory.config import get_settings
from agent_factory.infra.queue import (
    QUEUE_ZSET,
    ack_model_request,
    dequeue_model_request,
    enqueue_model_request,
    get_queue_length,
)


async def _redis():
    s = get_settings()
    return Redis.from_url(s.REDIS_URL, decode_responses=True)


@pytest.fixture
async def redis_client():
    r = await _redis()
    yield r
    await r.delete(QUEUE_ZSET)
    await r.aclose()


@pytest.mark.asyncio
async def test_enqueue_dequeue(redis_client):
    job_id = await enqueue_model_request(
        run_id="run_1",
        session_id="sess_1",
        agent_id="agent_1",
        priority_class="interactive",
        model="qwen3-32b",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
        _redis=redis_client,
    )
    assert job_id.startswith("job_")

    job = await dequeue_model_request(_redis=redis_client)
    assert job is not None
    assert job["run_id"] == "run_1"
    assert job["messages"][0]["content"] == "hi"
    await ack_model_request(job_id, _redis=redis_client)


@pytest.mark.asyncio
async def test_priority_ordering(redis_client):
    j1 = await enqueue_model_request(
        run_id="r1", session_id="s1", agent_id="a1",
        priority_class="batch", model="m", messages=[], max_tokens=10,
        _redis=redis_client,
    )
    j2 = await enqueue_model_request(
        run_id="r2", session_id="s2", agent_id="a2",
        priority_class="privileged", model="m", messages=[], max_tokens=10,
        _redis=redis_client,
    )
    job = await dequeue_model_request(_redis=redis_client)
    # privileged (score 1) should come before batch (score 4)
    assert job["run_id"] == "r2"
    await dequeue_model_request(_redis=redis_client)
    await ack_model_request(j1, _redis=redis_client)
    await ack_model_request(j2, _redis=redis_client)


@pytest.mark.asyncio
async def test_queue_length(redis_client):
    # Clear first
    await redis_client.delete(QUEUE_ZSET)
    j = await enqueue_model_request(
        run_id="r1", session_id="s1", agent_id="a1",
        priority_class="interactive", model="m", messages=[], max_tokens=10,
        _redis=redis_client,
    )
    length = await get_queue_length(_redis=redis_client)
    assert length == 1
    await dequeue_model_request(_redis=redis_client)
    await ack_model_request(j, _redis=redis_client)
