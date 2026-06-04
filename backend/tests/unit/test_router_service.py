"""Tests for Router Agent service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.db.models.agent_app import AgentApp
from agent_factory.services.router_service import route_to_agent


@pytest.mark.asyncio
async def test_route_to_agent_keyword_match(monkeypatch):
    monkeypatch.setenv("ROUTER_AGENT_ENABLED", "true")
    from agent_factory.config import get_settings

    get_settings.cache_clear()

    ag1 = MagicMock(spec=AgentApp)
    ag1.id = "contract-review-agent"
    ag1.name = "合同审查"
    ag1.instruction = "审查合同条款"
    ag1.owner = "legal"
    ag1.lifecycle_state = "active"

    ag2 = MagicMock(spec=AgentApp)
    ag2.id = "policy-qa-agent"
    ag2.name = "制度问答"
    ag2.instruction = "制度"
    ag2.owner = "hr"
    ag2.lifecycle_state = "active"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [ag1, ag2]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)

    monkeypatch.setenv("ROUTER_USE_LLM", "false")
    get_settings.cache_clear()

    out = await route_to_agent(
        db,
        user_message="请帮我审查这份合同",
        candidate_agent_ids=["contract-review-agent", "policy-qa-agent"],
        department="legal",
        model_gateway=None,
    )
    assert out["agent_id"] == "contract-review-agent"
    assert out["router"] == "keyword_v1"
