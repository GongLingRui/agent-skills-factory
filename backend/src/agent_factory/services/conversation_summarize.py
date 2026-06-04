"""LLM-backed dialog / tool compression (docs/08 summarization path)."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_factory.services.model_gateway import ModelGateway

logger = logging.getLogger(__name__)


async def collect_completion_text(
    model_gateway: ModelGateway,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 1024,
    temperature: float = 0.2,
    concurrency_class: str = "batch",
    queue_priority: int = 1,
) -> str:
    """Non-streaming aggregate of assistant deltas (internal summarizer calls)."""
    buf: list[str] = []
    try:
        async for chunk in model_gateway.chat(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=None,
            concurrency_class=concurrency_class,
            queue_priority=queue_priority,
        ):
            for choice in chunk.choices:
                d = choice.delta
                if d:
                    buf.append(d)
    except Exception:
        logger.exception("summarization_model_call_failed")
        raise
    return "".join(buf).strip()


def format_messages_plain(messages: list[dict[str, Any]], *, max_chars: int) -> str:
    """Linearize user/assistant rows for summarizer input."""
    lines: list[str] = []
    used = 0
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        c = m.get("content")
        text = c if isinstance(c, str) else ("" if c is None else str(c))
        block = f"{role.upper()}:\n{text}\n"
        if used + len(block) > max_chars:
            remain = max(0, max_chars - used - 40)
            if remain > 0:
                lines.append(f"{role.upper()}:\n{text[:remain]}…\n")
            break
        lines.append(block)
        used += len(block)
    return "\n".join(lines)


async def summarize_dialog_chunk(
    model_gateway: ModelGateway,
    *,
    model: str,
    transcript: str,
    max_out_tokens: int,
) -> str:
    """Produce a compact Chinese summary of *transcript*."""
    cap = max(256, min(4096, max_out_tokens * 4))
    body = transcript[: max(1, cap * 3)]
    sys_msg = (
        "你是对话压缩助手。将用户给出的多轮对话压缩为一条「记忆卡」："
        "保留事实、决定、待办、专有名词与数字；用中文要点列表或短段落；"
        "不要开场白、不要重复提示词。"
    )
    user_msg = f"以下待压缩对话：\n\n{body}"
    out = await collect_completion_text(
        model_gateway,
        model=model,
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=max_out_tokens,
        temperature=0.15,
        concurrency_class="batch",
        queue_priority=1,
    )
    if not out:
        return "[本会话较早内容 · 摘要暂不可用，请重试或缩短输入。]"
    return out


async def merge_cross_session_summary(
    model_gateway: ModelGateway,
    *,
    model: str,
    prior_summary: str,
    latest_exchange: str,
    max_out_tokens: int,
) -> str:
    """Roll prior memory card forward with the latest user/assistant exchange."""
    sys_msg = (
        "你是「跨会话记忆卡」维护助手。在已有记忆卡基础上合并本轮新信息："
        "去重、保留关键事实与未决事项；中文输出；不要开场白。"
    )
    user_msg = (
        f"【已有记忆卡】\n{prior_summary or '（空）'}\n\n"
        f"【本轮新增对话】\n{latest_exchange}\n\n"
        "请输出更新后的完整记忆卡（纯文本）。"
    )
    out = await collect_completion_text(
        model_gateway,
        model=model,
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg[:24000]},
        ],
        max_tokens=max_out_tokens,
        temperature=0.15,
        concurrency_class="batch",
        queue_priority=1,
    )
    if not out:
        ps = (prior_summary or "").strip()
        if ps:
            return ps + "\n\n[本轮合并失败：已保留历史记忆卡；请稍后重试。]"
        return "[跨会话摘要暂不可用]"
    return out


async def merge_cross_session_segments(
    model_gateway: ModelGateway,
    *,
    model: str,
    prior_segments: dict[str, Any],
    latest_exchange: str,
    max_out_tokens: int,
) -> dict[str, Any]:
    """Segmented merge: generate segment diff then merge with prior.

    Returns merged segments dict with keys: facts, preferences, decisions, todos, terms.
    """
    sys_msg = (
        "你是「跨会话记忆卡」维护助手。根据本轮新增对话，输出 JSON 格式的记忆更新："
        "字段：facts（关键事实列表）、preferences（用户偏好列表）、"
        "decisions（已确认决定列表）、todos（待办事项列表）、"
        "terms（专有名词列表，每项为 {name, definition}）。"
        "不要开场白，只输出 JSON。"
    )
    prior_text = _segments_to_text(prior_segments)
    user_msg = (
        f"【已有记忆】\n{prior_text or '（空）'}\n\n"
        f"【本轮新增对话】\n{latest_exchange[:12000]}\n\n"
        "请输出 JSON 格式的更新后记忆。"
    )
    try:
        out = await collect_completion_text(
            model_gateway,
            model=model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=max_out_tokens,
            temperature=0.15,
            concurrency_class="batch",
            queue_priority=1,
        )
    except Exception:
        logger.exception("merge_cross_session_segments_failed")
        return dict(prior_segments)

    out = out.strip()
    if not out:
        return dict(prior_segments)

    # Strip markdown fences
    if out.startswith("```"):
        lines = out.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        out = "\n".join(lines)

    try:
        parsed = json.loads(out)
        if isinstance(parsed, dict):
            return {
                "facts": _dedupe_str_list(
                    _to_str_list(prior_segments.get("facts"))
                    + _to_str_list(parsed.get("facts"))
                ),
                "preferences": _dedupe_str_list(
                    _to_str_list(prior_segments.get("preferences"))
                    + _to_str_list(parsed.get("preferences"))
                ),
                "decisions": _dedupe_str_list(
                    _to_str_list(prior_segments.get("decisions"))
                    + _to_str_list(parsed.get("decisions"))
                ),
                "todos": _dedupe_str_list(
                    _to_str_list(prior_segments.get("todos"))
                    + _to_str_list(parsed.get("todos"))
                ),
                "terms": _merge_terms(
                    prior_segments.get("terms"), parsed.get("terms")
                ),
            }
    except json.JSONDecodeError:
        logger.warning("merge_cross_session_segments_json_parse_failed")

    return dict(prior_segments)


async def summarize_tool_json_with_model(
    model_gateway: ModelGateway,
    *,
    model: str,
    raw_json: str,
    max_out_tokens: int = 512,
) -> str:
    """Compress huge tool JSON via model instead of middle truncation."""
    sys_msg = (
        "将工具返回的 JSON 压缩为简短中文要点列表，保留字段名、关键数值与"
        "错误码；不要复述整段 JSON。"
    )
    user_msg = f"JSON（可截断输入）：\n{raw_json[:16000]}"
    out = await collect_completion_text(
        model_gateway,
        model=model,
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=max_out_tokens,
        temperature=0.1,
        concurrency_class="batch",
        queue_priority=1,
    )
    return out or "[工具结果摘要暂不可用]"


def _segments_to_text(segments: dict[str, Any] | None) -> str:
    """Render segments dict to plain text for model input."""
    if not segments:
        return ""
    parts: list[str] = []
    for key in ("facts", "preferences", "decisions", "todos"):
        vals = segments.get(key)
        if vals:
            parts.append(f"【{key}】")
            for v in vals:
                parts.append(f"- {v}")
    terms = segments.get("terms")
    if terms:
        parts.append("【terms】")
        for t in terms:
            if isinstance(t, dict):
                parts.append(f"- {t.get('name', '')}：{t.get('definition', '')}")
    return "\n".join(parts)


def _to_str_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(v) for v in val if v is not None]
    return []


def _dedupe_str_list(vals: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in vals:
        low = v.lower().strip()
        if low and low not in seen:
            seen.add(low)
            out.append(v)
    # Cap each segment to avoid unbounded growth
    return out[:200]


def _merge_terms(
    prior: Any, latest: Any
) -> list[dict[str, str]]:
    out: dict[str, str] = {}
    for source in (prior, latest):
        if not isinstance(source, list):
            continue
        for t in source:
            if isinstance(t, dict):
                name = str(t.get("name") or "").strip()
                definition = str(t.get("definition") or "").strip()
                if name:
                    out[name] = definition
    return [{"name": k, "definition": v} for k, v in out.items()][:100]
