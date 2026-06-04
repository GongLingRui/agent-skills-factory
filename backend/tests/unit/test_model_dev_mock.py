"""MODEL_DEV_MOCK stream (local dev, no vendor HTTP)."""

import pytest
from agent_factory.services.model_gateway import ModelGateway, _dev_mock_chat_stream


@pytest.mark.asyncio
async def test_dev_mock_stream_echoes_user():
    chunks: list = []
    async for c in _dev_mock_chat_stream(
        [{"role": "user", "content": "hello mock"}],
    ):
        chunks.append(c)
    assert len(chunks) == 2
    assert chunks[0].choices[0].delta.startswith("[本地开发 MOCK")
    assert "hello mock" in chunks[0].choices[0].delta
    assert chunks[1].choices[0].finish_reason == "stop"
    assert chunks[1].usage is not None


@pytest.mark.asyncio
async def test_model_gateway_respects_mock_flag(monkeypatch):
    monkeypatch.setenv("MODEL_DEV_MOCK", "true")
    monkeypatch.setenv("APP_ENV", "development")
    from agent_factory.config.settings import get_settings

    get_settings.cache_clear()
    gw = ModelGateway(get_settings())

    async def _run():
        out = []
        async for c in gw._chat_stream(
            model="qwen3-32b",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=100,
            temperature=0.0,
            tools=None,
        ):
            out.append(c)
        return out

    chunks = await _run()
    get_settings.cache_clear()
    assert any("ping" in (x.choices[0].delta or "") for x in chunks if x.choices)
