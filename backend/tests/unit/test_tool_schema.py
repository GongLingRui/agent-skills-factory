"""Tests for OpenAI tool schema builder."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_factory.core.tool_schema import build_tools_for_chat_api


@pytest.mark.asyncio
async def test_read_reference_schema_uses_lazy_name_enum():
    row = MagicMock()
    row.id = "read_reference"
    row.name = "读取 Skill 引用"
    row.description = "按名称读取 reference"
    row.input_schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    q = MagicMock()
    q.all.return_value = [row]
    db = MagicMock()
    db.execute = AsyncMock(return_value=q)

    tools = await build_tools_for_chat_api(
        db,
        ["read_reference"],
        lazy_reference_names=["fsm-state-contracts", "pattern-library"],
    )
    assert tools is not None
    params = tools[0]["function"]["parameters"]
    assert params["properties"]["name"]["enum"] == [
        "fsm-state-contracts",
        "pattern-library",
    ]
