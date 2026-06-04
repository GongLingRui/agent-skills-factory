"""Model gateway fallback chain (multi-hop + defaults fallback)."""

import pytest

from agent_factory.infra.model_client import ChatChunk, ChatChoice, ModelClientError
from agent_factory.services.model_gateway import ModelGateway


def test_chat_attempt_chain_appends_default_fallback(monkeypatch):
    monkeypatch.setenv("MODEL_DEV_MOCK", "false")
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    gw = ModelGateway(get_settings())
    chain = gw._chat_attempt_chain("qwen3-32b")
    assert chain[0] == "qwen3-32b"
    assert "qwen3-14b" in chain
    assert "qwen3-8b" in chain
    assert chain[-1] == "MiniMax-M2.7"


@pytest.mark.asyncio
async def test_chat_stream_advances_chain_until_success(monkeypatch):
    monkeypatch.setenv("MODEL_DEV_MOCK", "false")
    monkeypatch.setenv("APP_ENV", "production")
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    gw = ModelGateway(get_settings())

    attempts: list[str] = []

    async def fake_chat(
        self,
        *,
        model,
        messages,
        max_tokens=None,
        temperature=None,
        tools=None,
        stream=True,
    ):
        attempts.append(model)
        if model != "MiniMax-M2.7":
            raise ModelClientError("upstream down")
        yield ChatChunk(
            choices=[ChatChoice(delta="ok", finish_reason="stop")],
            model=model,
        )

    monkeypatch.setattr(
        "agent_factory.services.model_gateway.ModelClient.chat_completions",
        fake_chat,
        raising=False,
    )

    chunks: list[ChatChunk] = []
    async for c in gw._chat_stream(
        model="qwen3-32b",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=10,
        temperature=0.0,
        tools=None,
    ):
        chunks.append(c)

    get_settings.cache_clear()
    assert "MiniMax-M2.7" in attempts
    assert attempts[-1] == "MiniMax-M2.7"
    assert chunks and chunks[0].choices[0].delta == "ok"
