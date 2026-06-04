"""LLM-based Router Agent (prd P3)."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_factory.core.model_output_parse import extract_json_object_from_text
from agent_factory.db.models.agent_app import AgentApp
from agent_factory.services.model_gateway import ModelGateway

logger = logging.getLogger(__name__)


def _catalog(agents: list[AgentApp]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for ag in agents:
        out.append(
            {
                "agent_id": ag.id,
                "name": (ag.name or ag.id)[:128],
                "summary": ((ag.instruction or "")[:400]),
            }
        )
    return out


async def _collect_chat_text(
    gateway: ModelGateway,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
) -> str:
    parts: list[str] = []
    async for chunk in gateway.chat(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.0,
        tools=None,
        concurrency_class="batch",
        queue_priority=3,
    ):
        for choice in chunk.choices:
            if choice.delta:
                parts.append(choice.delta)
    return "".join(parts).strip()


async def route_with_llm(
    gateway: ModelGateway,
    *,
    user_message: str,
    agents: list[AgentApp],
    model: str,
    max_tokens: int = 256,
) -> dict[str, Any] | None:
    """Return routing dict or ``None`` if model output unusable."""
    catalog = _catalog(agents)
    allowed_ids = {a.id for a in agents}
    system = (
        "你是企业 Agent 路由器。根据用户意图从候选列表中选择唯一 agent_id。"
        "只输出 JSON 对象："
        '{"agent_id":"<id>","confidence":0.0-1.0,"reason":"简短中文"}'
    )
    user = (
        f"候选：\n{json.dumps(catalog, ensure_ascii=False)}\n\n"
        f"用户消息：{user_message}"
    )
    text = await _collect_chat_text(
        gateway,
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )
    obj = extract_json_object_from_text(text)
    if not obj:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(obj, dict):
        return None
    aid = str(obj.get("agent_id") or "").strip()
    if aid not in allowed_ids:
        return None
    conf = obj.get("confidence", 0.7)
    try:
        confidence = float(conf)
    except (TypeError, ValueError):
        confidence = 0.7
    return {
        "agent_id": aid,
        "confidence": max(0.0, min(1.0, confidence)),
        "router": "llm_v1",
        "reason": str(obj.get("reason") or "")[:500],
        "candidates": list(allowed_ids),
    }
