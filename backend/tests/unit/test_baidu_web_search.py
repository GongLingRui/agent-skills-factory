"""Tests for Baidu web.search integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent_factory.config import Settings
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.baidu_web_search_client import post_baidu_web_search
from agent_factory.services.tool_gateway import ToolGateway


@pytest.mark.asyncio
async def test_post_baidu_web_search_normalizes_results() -> None:
    settings = Settings.model_construct(
        WEB_SEARCH_ENABLED=True,
        BAIDU_WEB_SEARCH_API_KEY="bce-v3/test-key",
        BAIDU_WEB_SEARCH_DEFAULT_TOP_K=10,
    )

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {
                "request_id": "req-1",
                "references": [
                    {
                        "id": 1,
                        "title": "示例标题",
                        "url": "https://example.com/a",
                        "content": "摘要内容",
                        "date": "2025-01-01",
                        "type": "web",
                    }
                ],
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, json: dict, headers: dict):
            assert "web_search" in url
            assert headers["Authorization"].startswith("Bearer bce-v3/")
            assert json["messages"][0]["content"] == "北京天气"
            return _Resp()

    with patch(
        "agent_factory.services.baidu_web_search_client.httpx.AsyncClient",
        return_value=_Client(),
    ):
        out = await post_baidu_web_search(settings, query="北京天气", top_k=5)

    assert out["provider"] == "baidu_qianfan"
    assert out["total"] == 1
    assert out["results"][0]["title"] == "示例标题"
    assert out["results"][0]["snippet"] == "摘要内容"


@pytest.mark.asyncio
async def test_post_baidu_web_search_requires_api_key() -> None:
    settings = Settings.model_construct(
        WEB_SEARCH_ENABLED=True,
        BAIDU_WEB_SEARCH_API_KEY="",
    )
    with pytest.raises(AgentFactoryException) as exc:
        await post_baidu_web_search(settings, query="test")
    assert exc.value.code == "WEB_SEARCH_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_tool_gateway_web_search() -> None:
    settings = Settings.model_construct(
        WEB_SEARCH_ENABLED=True,
        BAIDU_WEB_SEARCH_API_KEY="bce-v3/test-key",
    )
    gw = ToolGateway()
    with patch(
        "agent_factory.services.workspace_tools.post_baidu_web_search",
        new=AsyncMock(
            return_value={
                "query": "agent factory",
                "results": [],
                "total": 0,
            }
        ),
    ), patch(
        "agent_factory.services.tool_gateway.get_settings",
        return_value=settings,
    ):
        out = await gw.validate_and_run_async(
            db=AsyncMock(),
            tool_id="web.search",
            params={"query": "agent factory"},
            allowed_tools=["web.search"],
            retrieval_scopes=[],
        )
    assert out["query"] == "agent factory"
