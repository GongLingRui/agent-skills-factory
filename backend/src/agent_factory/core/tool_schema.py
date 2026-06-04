"""Tool schema generation for OpenAI-compatible chat API (Stage A)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_factory.core.tool_catalog import TOOL_BY_ID, input_schema_for_tool
from agent_factory.db.models.tool import Tool

logger = logging.getLogger(__name__)


async def build_tools_for_chat_api(
    db: AsyncSession,
    allowed_tools: list[str],
    *,
    lazy_reference_names: list[str] | None = None,
) -> list[dict[str, Any]] | None:
    """Query Tool Registry and build OpenAI-compatible ``tools`` parameter.

    Only returns tools that have active registry rows with an ``input_schema``.
    Built-in tools (e.g. ``doc.extract``) are expected to be described in the
    system prompt and do not need a registry schema entry.

    Returns ``None`` if no matching registry rows are found so the caller can
    fall back to ``tools=None`` (legacy text-parsing mode).
    """
    if not allowed_tools:
        return None
    q = await db.execute(
        select(Tool.id, Tool.name, Tool.description, Tool.input_schema).where(
            Tool.id.in_(allowed_tools),
            Tool.status == "active",
        )
    )
    rows = q.all()
    tools: list[dict[str, Any]] = []
    found_ids: set[str] = set()
    for row in rows:
        found_ids.add(row.id)
        schema = row.input_schema if isinstance(row.input_schema, dict) else {}
        params = dict(schema) if schema else {"type": "object", "properties": {}}
        description = row.description or row.name or row.id
        if row.id == "read_reference" and lazy_reference_names:
            props = dict(params.get("properties") or {})
            props["name"] = {
                "type": "string",
                "description": (
                    "reference 名称（不含路径和扩展名）；"
                    f"可选值：{', '.join(lazy_reference_names)}"
                ),
                "enum": list(lazy_reference_names),
            }
            params = {**params, "properties": props}
            description = (
                "读取 Skill 包内 on_demand reference 正文（非用户上传附件）。"
                "name 必须使用 lazy_references 白名单中的短名称。"
            )
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": row.id,
                    "description": description,
                    "parameters": params,
                },
            }
        )

    for tool_id in allowed_tools:
        if tool_id in found_ids:
            continue
        desc = TOOL_BY_ID.get(tool_id)
        if desc is None or not desc.implemented:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool_id,
                    "description": desc.description,
                    "parameters": input_schema_for_tool(tool_id),
                },
            }
        )
    return tools if tools else None
