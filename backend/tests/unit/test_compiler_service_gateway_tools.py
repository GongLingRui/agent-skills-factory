"""CompilerService gateway tool catalog (built-ins + Tool Registry)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.config.settings import get_settings
from agent_factory.services.compiler_service import CompilerService


@pytest.mark.asyncio
async def test_gateway_available_tool_ids_unions_registry(monkeypatch):
    monkeypatch.setenv("MODEL_DEV_MOCK", "true")
    get_settings.cache_clear()
    try:
        svc = CompilerService(get_settings())
        db = AsyncMock()
        res = MagicMock()
        res.scalars.return_value.all.return_value = [
            "custom.http.tool",
            "kb.search",
        ]
        db.execute = AsyncMock(return_value=res)
        ids = await svc._gateway_available_tool_ids(db)
        assert set(ids) >= {
            "kb.search",
            "doc.extract",
            "read_reference",
            "risk.rule_check",
            "custom.http.tool",
        }
        assert ids == sorted(ids)
        assert len(ids) == len(set(ids))
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_gateway_available_tool_ids_empty_registry(monkeypatch):
    monkeypatch.setenv("MODEL_DEV_MOCK", "true")
    get_settings.cache_clear()
    try:
        svc = CompilerService(get_settings())
        db = AsyncMock()
        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=res)
        ids = await svc._gateway_available_tool_ids(db)
        assert set(ids) == set(svc.tool_gateway._handlers.keys())
    finally:
        get_settings.cache_clear()
