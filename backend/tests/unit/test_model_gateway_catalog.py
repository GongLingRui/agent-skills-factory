"""Model catalog, aliases, and api_model routing."""

import pytest

from agent_factory.infra.model_client import ChatChoice, ChatChunk
from agent_factory.services.model_gateway import ModelGateway


def test_expand_alias_default(monkeypatch):
    monkeypatch.setenv("MODEL_DEV_MOCK", "false")
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    gw = ModelGateway(get_settings())
    assert gw.expand_alias("default") == "MiniMax-M2.7"
    assert gw.expand_alias("minimax") == "MiniMax-M2.7"
    assert gw.is_logical_model_configured("default") is True


def test_list_model_catalog_non_empty(monkeypatch):
    monkeypatch.setenv("MODEL_DEV_MOCK", "false")
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    gw = ModelGateway(get_settings())
    cat = gw.list_model_catalog()
    ids = {m["id"] for m in cat}
    assert "MiniMax-M2.7" in ids
    assert all("provider" in m and "api_model" in m for m in cat)


@pytest.mark.asyncio
async def test_chat_stream_uses_api_model_id(monkeypatch):
    monkeypatch.setenv("MODEL_DEV_MOCK", "false")
    monkeypatch.setenv("APP_ENV", "production")
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    gw = ModelGateway(get_settings())
    gw._models["MiniMax-M2.7"].api_model = "vendor-body-id-xyz"

    seen: list[str] = []

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
        seen.append(model)
        yield ChatChunk(
            choices=[ChatChoice(delta="x", finish_reason="stop")],
            model=model,
        )

    monkeypatch.setattr(
        "agent_factory.services.model_gateway.ModelClient.chat_completions",
        fake_chat,
        raising=False,
    )

    async for _ in gw._chat_stream(
        model="MiniMax-M2.7",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=10,
        temperature=0.0,
        tools=None,
    ):
        pass

    get_settings.cache_clear()
    assert seen == ["vendor-body-id-xyz"]
