"""Tests for reactive compact (prompt_too_long handling)."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from agent_factory.infra.model_client import PromptTooLongError
from agent_factory.infra.model_queue import acquire_model_queue_slot
from agent_factory.services.model_gateway import ModelGateway


class FakeSettings:
    MODELS_CONFIG_PATH = "/dev/null"
    MODEL_DEV_MOCK = True
    APP_ENV = "development"
    MODEL_QUEUE_ENABLED = False


class FakeModelGateway(ModelGateway):
    def __init__(self):
        # bypass yaml load
        self.settings = FakeSettings()
        self._models = {}
        self._clients = {}
        self._defaults = {}
        self._aliases = {}

    async def _chat_stream(self, **kwargs):
        if True:
            raise PromptTooLongError("context too long")
        yield None  # make it an async generator


@pytest.fixture(autouse=True)
def bypass_model_queue(monkeypatch):
    @asynccontextmanager
    async def _noop(*args, **kwargs):
        yield

    monkeypatch.setattr(
        "agent_factory.infra.model_queue.acquire_model_queue_slot", _noop
    )


@pytest.mark.anyio
async def test_prompt_too_long_error_is_raised():
    gw = FakeModelGateway()
    with pytest.raises(PromptTooLongError):
        async for _ in gw.chat(model="fake", messages=[{"role": "user", "content": "x"}]):
            pass
