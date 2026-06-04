"""Registry-backed http_api tools (docs/09)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent_factory.config.settings import get_settings
from agent_factory.db.models.run_spec import RunSpec
from agent_factory.db.models.tool import Tool
from agent_factory.middleware.error_handler import AgentFactoryException
from agent_factory.services.tool_gateway import ToolGateway


class _FakeRedis:
    """Minimal Redis stub for circuit breaker hooks."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ints: dict[str, int] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, val: str, ex: int | None = None):
        self.store[key] = val

    async def incr(self, key: str) -> int:
        self.ints[key] = self.ints.get(key, 0) + 1
        return self.ints[key]

    async def expire(self, key: str, sec: int) -> bool:
        return True

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)
        self.ints.pop(key, None)


@pytest.fixture
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_http_api_from_registry_ok(monkeypatch, clear_settings_cache):
    monkeypatch.setenv(
        "INTERNAL_HTTP_TOOL_URL_PREFIXES",
        "https://internal.example/",
    )
    get_settings.cache_clear()

    row = Tool(
        id="custom.echo",
        version="1.0.0",
        status="active",
        implementation={
            "type": "http_api",
            "endpoint": "https://internal.example/v1/echo",
        },
        timeout_seconds=5,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    gw = ToolGateway()
    mock_resp = httpx.Response(200, json={"echo": True})

    with (
        patch("httpx.AsyncClient") as client_cls,
        patch(
            "agent_factory.services.tool_gateway.get_redis",
            return_value=_FakeRedis(),
        ),
    ):
        inst = AsyncMock()
        client_cls.return_value.__aenter__.return_value = inst
        inst.post = AsyncMock(return_value=mock_resp)

        out = await gw.validate_and_run_async(
            mock_db,
            tool_id="custom.echo",
            params={"q": "hi"},
            allowed_tools=["custom.echo"],
            retrieval_scopes=[],
        )
    assert out == {"echo": True}


@pytest.mark.asyncio
async def test_http_api_disabled_without_prefix(monkeypatch, clear_settings_cache):
    monkeypatch.delenv("INTERNAL_HTTP_TOOL_URL_PREFIXES", raising=False)
    get_settings.cache_clear()

    row = Tool(
        id="custom.echo",
        version="1.0.0",
        status="active",
        implementation={
            "type": "http_api",
            "endpoint": "https://internal.example/v1/echo",
        },
        timeout_seconds=5,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    gw = ToolGateway()
    with (
        pytest.raises(AgentFactoryException) as ei,
        patch(
            "agent_factory.services.tool_gateway.get_redis",
            return_value=_FakeRedis(),
        ),
    ):
        await gw.validate_and_run_async(
            mock_db,
            tool_id="custom.echo",
            params={},
            allowed_tools=["custom.echo"],
            retrieval_scopes=[],
        )
    assert ei.value.code == "TOOL_HTTP_DISABLED"


@pytest.mark.asyncio
async def test_http_api_endpoint_not_allowlisted(monkeypatch, clear_settings_cache):
    monkeypatch.setenv(
        "INTERNAL_HTTP_TOOL_URL_PREFIXES",
        "https://allowed.only/",
    )
    get_settings.cache_clear()

    row = Tool(
        id="custom.echo",
        version="1.0.0",
        status="active",
        implementation={
            "type": "http_api",
            "endpoint": "https://evil.example/hook",
        },
        timeout_seconds=5,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    gw = ToolGateway()
    with (
        pytest.raises(AgentFactoryException) as ei,
        patch(
            "agent_factory.services.tool_gateway.get_redis",
            return_value=_FakeRedis(),
        ),
    ):
        await gw.validate_and_run_async(
            mock_db,
            tool_id="custom.echo",
            params={},
            allowed_tools=["custom.echo"],
            retrieval_scopes=[],
        )
    assert ei.value.code == "TOOL_HTTP_FORBIDDEN"


@pytest.mark.asyncio
async def test_http_api_circuit_open(monkeypatch, clear_settings_cache):
    monkeypatch.setenv(
        "INTERNAL_HTTP_TOOL_URL_PREFIXES",
        "https://internal.example/",
    )
    get_settings.cache_clear()

    row = Tool(
        id="custom.echo",
        version="1.0.0",
        status="active",
        implementation={
            "type": "http_api",
            "endpoint": "https://internal.example/v1/echo",
        },
        timeout_seconds=5,
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    fr = _FakeRedis()
    await fr.set("cb:httptool:custom.echo:open", "1")

    gw = ToolGateway()
    with (
        pytest.raises(AgentFactoryException) as ei,
        patch(
            "agent_factory.services.tool_gateway.get_redis",
            return_value=fr,
        ),
    ):
        await gw.validate_and_run_async(
            mock_db,
            tool_id="custom.echo",
            params={},
            allowed_tools=["custom.echo"],
            retrieval_scopes=[],
        )
    assert ei.value.code == "TOOL_CIRCUIT_OPEN"


@pytest.mark.asyncio
async def test_http_api_registry_403_when_permission_required_missing(
    monkeypatch, clear_settings_cache
):
    monkeypatch.setenv(
        "INTERNAL_HTTP_TOOL_URL_PREFIXES",
        "https://internal.example/",
    )
    get_settings.cache_clear()

    row = Tool(
        id="custom.echo",
        version="1.0.0",
        status="active",
        implementation={
            "type": "http_api",
            "endpoint": "https://internal.example/v1/echo",
        },
        timeout_seconds=5,
        permission_required=["knowledge.read"],
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    gw = ToolGateway()
    with pytest.raises(AgentFactoryException) as ei:
        await gw.validate_and_run_async(
            mock_db,
            tool_id="custom.echo",
            params={"q": "hi"},
            allowed_tools=["custom.echo"],
            retrieval_scopes=[],
            caller_permissions=frozenset(),
        )
    assert ei.value.status_code == 403
    assert ei.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_http_api_registry_ok_when_permission_required_satisfied(
    monkeypatch, clear_settings_cache
):
    monkeypatch.setenv(
        "INTERNAL_HTTP_TOOL_URL_PREFIXES",
        "https://internal.example/",
    )
    get_settings.cache_clear()

    row = Tool(
        id="custom.echo",
        version="1.0.0",
        status="active",
        implementation={
            "type": "http_api",
            "endpoint": "https://internal.example/v1/echo",
        },
        timeout_seconds=5,
        permission_required=["knowledge.read"],
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    gw = ToolGateway()
    mock_resp = httpx.Response(200, json={"echo": True})

    with (
        patch("httpx.AsyncClient") as client_cls,
        patch(
            "agent_factory.services.tool_gateway.get_redis",
            return_value=_FakeRedis(),
        ),
    ):
        inst = AsyncMock()
        client_cls.return_value.__aenter__.return_value = inst
        inst.post = AsyncMock(return_value=mock_resp)

        out = await gw.validate_and_run_async(
            mock_db,
            tool_id="custom.echo",
            params={"q": "hi"},
            allowed_tools=["custom.echo"],
            retrieval_scopes=[],
            caller_permissions=frozenset({"knowledge.read"}),
        )
    assert out == {"echo": True}


@pytest.mark.asyncio
async def test_kb_search_upstream_post_includes_indexed_references(
    monkeypatch, clear_settings_cache
):
    monkeypatch.setenv("KB_SEARCH_URL", "https://kb.example/v1/search")
    monkeypatch.setenv("MODEL_QUEUE_ENABLED", "false")
    get_settings.cache_clear()

    idx = [{"name": "doc1", "scope": "legal"}]
    rs = RunSpec(
        run_id="run_kb_idx",
        runspec_schema_version=1,
        agent_id="ag",
        agent_version="1",
        skill_id="sk1",
        skill_version="1.0.0",
        skill_package_hash="",
        user_id_hash="u",
        skill_file_manifest={},
        indexed_references=idx,
        allowed_tools=["kb.search"],
    )
    mock_db = AsyncMock()
    mock_resp = httpx.Response(
        200, json={"results": [{"id": "1"}], "total": 1},
    )
    gw = ToolGateway()

    class _FakeBroker:
        async def embed_text(self, _t: str) -> list[float]:
            return [0.0, 0.0]

    with (
        patch("httpx.AsyncClient") as client_cls,
        patch(
            "agent_factory.services.tool_gateway.get_embedding_broker",
            return_value=_FakeBroker(),
        ),
    ):
        inst = AsyncMock()
        client_cls.return_value.__aenter__.return_value = inst
        inst.post = AsyncMock(return_value=mock_resp)
        await gw.validate_and_run_async(
            mock_db,
            tool_id="kb.search",
            params={"query": "q1"},
            allowed_tools=["kb.search"],
            retrieval_scopes=["s1"],
            run_spec=rs,
        )
    inst.post.assert_called_once()
    sent = inst.post.call_args.kwargs.get("json") or {}
    assert sent.get("indexed_references") == [
        {"name": "doc1", "scope": "legal"},
    ]
    assert sent.get("query") == "q1"
    assert sent.get("retrieval_scopes") == ["s1"]
