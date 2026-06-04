"""Custom Prometheus gauges (docs/32, plan §13.2)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_factory.infra.prometheus_gauge_refresh import refresh_prometheus_gauges
from agent_factory.infra.prometheus_registry import (
    AF_DEGRADATION_LEVEL,
    AF_DOC_PARSE_STREAM_MESSAGES,
    AF_MODEL_INFLIGHT,
    AF_MODEL_QUEUE_LENGTH,
)


@pytest.mark.asyncio
async def test_refresh_sets_gauges_from_redis():
    redis = MagicMock()
    redis.xlen = AsyncMock(return_value=7)
    redis.zcard = AsyncMock(side_effect=[1, 0, 2, 3])
    redis.get = AsyncMock(side_effect=[b"2", None, b"1", None])

    deg_state = MagicMock()
    deg_state.level = 4
    deg_state.reason = "test"

    with patch(
        "agent_factory.infra.prometheus_gauge_refresh.get_redis",
        return_value=redis,
    ), patch(
        "agent_factory.infra.prometheus_gauge_refresh.DegradationService"
    ) as ds_cls:
        ds_cls.return_value.get_level = AsyncMock(return_value=deg_state)
        await refresh_prometheus_gauges()

    assert AF_DOC_PARSE_STREAM_MESSAGES._value.get() == 7.0
    assert AF_DEGRADATION_LEVEL._value.get() == 4.0
    assert redis.xlen.await_count == 1
    assert redis.zcard.await_count == 4


@pytest.mark.asyncio
async def test_refresh_sets_queue_labels():
    redis = MagicMock()
    redis.xlen = AsyncMock(return_value=0)
    redis.zcard = AsyncMock(return_value=0)
    redis.get = AsyncMock(return_value=None)

    with patch(
        "agent_factory.infra.prometheus_gauge_refresh.get_redis",
        return_value=redis,
    ), patch(
        "agent_factory.infra.prometheus_gauge_refresh.DegradationService"
    ) as ds_cls:
        ds_cls.return_value.get_level = AsyncMock(
            return_value=MagicMock(level=0, reason="")
        )
        await refresh_prometheus_gauges()

    for cls in ("privileged", "interactive", "document", "batch"):
        assert AF_MODEL_QUEUE_LENGTH.labels(concurrency_class=cls)._value.get() == 0.0
        assert AF_MODEL_INFLIGHT.labels(concurrency_class=cls)._value.get() == 0.0
