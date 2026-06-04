"""Generate a Tool Use Summary after multiple tool calls in one turn."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_factory.services.conversation_summarize import collect_completion_text
from agent_factory.services.model_gateway import ModelGateway

logger = logging.getLogger(__name__)


async def generate_tool_use_summary(
    model_gateway: ModelGateway,
    model: str,
    tool_results: list[dict[str, Any]],
    max_tokens: int = 256,
) -> str:
    """Produce a short Chinese summary of tool calls and their results.

    *tool_results* is a list of dicts with keys:
      - tool_id: str
      - call_id: str
      - result_preview: str  (truncated or full result)
    """
    if not tool_results:
        return ""

    lines: list[str] = []
    for tr in tool_results:
        tid = tr.get("tool_id", "")
        preview = tr.get("result_preview", "")
        lines.append(f"工具 {tid}：{preview[:400]}")

    body = "\n".join(lines)
    sys_msg = (
        "你是「工具调用摘要助手」。简要总结本轮工具调用的目的与核心结果，"
        "用 1-2 句中文；不要重复原始 JSON；不要开场白。"
    )
    user_msg = f"本轮工具调用：\n\n{body}"
    try:
        out = await collect_completion_text(
            model_gateway,
            model=model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=max_tokens,
            temperature=0.15,
            concurrency_class="batch",
            queue_priority=1,
        )
    except Exception:
        logger.exception("tool_use_summary_generation_failed")
        return ""
    return out.strip() or ""
