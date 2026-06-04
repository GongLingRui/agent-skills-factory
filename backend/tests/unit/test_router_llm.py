"""Tests for LLM router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.infra.model_client import ChatChoice, ChatChunk
from agent_factory.services.router_llm import route_with_llm


@pytest.mark.asyncio
async def test_route_with_llm_parses_json():
    ag = MagicMock()
    ag.id = "a1"
    ag.name = "合同"
    ag.instruction = "审查"

    async def _fake_chat(**_kwargs):
        yield ChatChunk(
            choices=[
                ChatChoice(
                    delta='{"agent_id":"a1","confidence":0.92,"reason":"匹配"}',
                    finish_reason="stop",
                )
            ]
        )

    gw = MagicMock()
    gw.chat = _fake_chat

    out = await route_with_llm(
        gw,
        user_message="审查合同",
        agents=[ag],
        model="test-model",
    )
    assert out is not None
    assert out["agent_id"] == "a1"
    assert out["router"] == "llm_v1"
    assert out["confidence"] >= 0.9
