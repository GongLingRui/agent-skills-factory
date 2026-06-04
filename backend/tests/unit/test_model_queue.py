"""Model queue slot acquire (docs/10 skeleton)."""

import pytest

from agent_factory.config.settings import Settings
from agent_factory.infra.model_queue import acquire_model_queue_slot


@pytest.mark.asyncio
async def test_acquire_disabled_yields_without_redis_use():
    s = Settings.model_construct(MODEL_QUEUE_ENABLED=False)

    class _NoRedis:
        async def eval(self, *a, **k):
            raise AssertionError("redis should not be used")

    r = _NoRedis()
    async with acquire_model_queue_slot(r, s, "interactive"):
        pass
