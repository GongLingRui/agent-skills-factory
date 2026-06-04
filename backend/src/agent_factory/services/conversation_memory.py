"""Assemble chat messages for the model (summarize vs snip, tool payloads)."""

from __future__ import annotations

import copy
import logging
from typing import Any

from agent_factory.core.context_memory import (
    ContextMemorySettings,
    apply_history_snip,
    estimate_messages_chars,
    split_tail_by_user_turns,
    truncate_middle_chars,
    truncate_tool_json_payload,
)
from agent_factory.core.conversation_continue import tail_split_index_preserve_context
from agent_factory.services.conversation_summarize import (
    format_messages_plain,
    summarize_dialog_chunk,
    summarize_tool_json_with_model,
)
from agent_factory.services.model_gateway import ModelGateway
from agent_factory.services.tool_result_persistence import is_tool_result_stub

logger = logging.getLogger(__name__)

_ASSISTANT_HTML_CLAMP_CHARS = 72_000
_ASSISTANT_HTML_HEAD_CHARS = 20_000
_ASSISTANT_HTML_TAIL_CHARS = 20_000


def _compress_oversized_assistant_messages(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Shrink huge assistant turns (e.g. HTML decks) for the model payload."""
    out: list[dict[str, Any]] = []
    changed = False
    for row in messages:
        if row.get("role") != "assistant":
            out.append(copy.copy(row))
            continue
        content = row.get("content")
        if not isinstance(content, str) or len(content) <= _ASSISTANT_HTML_CLAMP_CHARS:
            out.append(copy.copy(row))
            continue
        changed = True
        shrunk = copy.copy(row)
        shrunk["content"] = truncate_middle_chars(
            content,
            max_chars=_ASSISTANT_HTML_CLAMP_CHARS,
            head_chars=_ASSISTANT_HTML_HEAD_CHARS,
            tail_chars=_ASSISTANT_HTML_TAIL_CHARS,
        )
        out.append(shrunk)
    return out, changed


async def prepare_messages_for_chat_api(
    messages: list[dict[str, Any]],
    cfg: ContextMemorySettings,
    model_gateway: ModelGateway,
    *,
    main_model: str,
) -> list[dict[str, Any]]:
    """Shrink *messages* for the model without mutating checkpoint source."""
    if not cfg.enabled:
        return [copy.copy(m) for m in messages]

    work = [copy.copy(m) for m in messages]
    smodel = cfg.summarization_model or main_model
    rounds = 0
    while (
        rounds < cfg.max_shrink_rounds
        and estimate_messages_chars(work) > cfg.history_budget_chars
    ):
        prev_chars = estimate_messages_chars(work)
        rounds += 1
        if cfg.compression == "snip":
            work = apply_history_snip(work, cfg)
            break

        prefix, tail = split_tail_by_user_turns(
            work,
            keep_user_turns=cfg.keep_recent_user_turns,
            min_user_turns=cfg.min_user_turns,
        )
        if not prefix:
            if len(work) <= 1:
                break
            split_at = tail_split_index_preserve_context(work)
            prefix, tail = work[:split_at], work[split_at:]
            if not prefix and len(work) >= 2:
                compressed, did_compress = _compress_oversized_assistant_messages(work)
                if did_compress:
                    work = compressed
                    continue
                work = apply_history_snip(work, cfg)
                break

        transcript = format_messages_plain(
            prefix,
            max_chars=cfg.summarize_input_cap_chars,
        )
        try:
            summary = await summarize_dialog_chunk(
                model_gateway,
                model=smodel,
                transcript=transcript,
                max_out_tokens=cfg.summary_max_output_tokens,
            )
        except Exception:
            logger.exception(
                "prepare_messages_summarize_failed_using_emergency_snip",
            )
            work = apply_history_snip(work, cfg)
            break

        boundary_pre = {
            "role": "system",
            "content": "[会话摘要边界开始] 以下内容为本会话较早对话的模型摘要，非原始用户消息。",
        }
        bubble = {
            "role": "user",
            "content": "[本会话较早内容 · 模型摘要]\n" + summary,
        }
        boundary_post = {
            "role": "system",
            "content": "[会话摘要边界结束] 以下为原始对话记录。",
        }
        work = [boundary_pre, bubble, boundary_post] + [copy.copy(x) for x in tail]
        if estimate_messages_chars(work) >= prev_chars:
            logger.warning("summarize_did_not_reduce_chars_emergency_snip")
            work = apply_history_snip(work, cfg)
            break

    return work


async def maybe_compact_tool_messages(
    messages: list[dict[str, Any]],
    cfg: ContextMemorySettings,
    model_gateway: ModelGateway,
    *,
    main_model: str,
) -> None:
    """In-place tool message compaction before each model call."""
    if not cfg.enabled:
        return
    if cfg.tool_compression == "truncate":
        from agent_factory.core.context_memory import clamp_tool_results_in_api_messages

        clamp_tool_results_in_api_messages(messages, cfg)
        return

    sm = cfg.summarization_model or main_model

    # Build a quick lookup of assistant messages by tool_call id so we can
    # skip compacting tool results whose assistant was already removed.
    assistant_by_tool_call_id: dict[str, dict[str, Any]] = {}
    for m in messages:
        if m.get("role") == "assistant":
            tcs = m.get("tool_calls")
            if isinstance(tcs, list):
                for tc in tcs:
                    tcid = tc.get("id")
                    if isinstance(tcid, str):
                        assistant_by_tool_call_id[tcid] = m

    for m in messages:
        if m.get("role") != "tool":
            continue
        c = m.get("content")
        if not isinstance(c, str) or len(c) <= cfg.tool_result_max_chars:
            continue
        if is_tool_result_stub(c):
            continue

        tcid = m.get("tool_call_id")
        if isinstance(tcid, str) and tcid not in assistant_by_tool_call_id:
            # Dangling tool result (assistant missing) – do not compact in
            # isolation to avoid further masking the structural issue.
            continue

        try:
            m["content"] = await summarize_tool_json_with_model(
                model_gateway,
                model=sm,
                raw_json=c,
                max_out_tokens=512,
            )
        except Exception:
            logger.exception("tool_json_summarize_failed_using_truncate")
            m["content"] = truncate_tool_json_payload(c, cfg)


async def tool_result_payload_for_api(
    result: dict[str, Any],
    cfg: ContextMemorySettings,
    model_gateway: ModelGateway,
    *,
    main_model: str,
) -> str:
    """Serialize a tool result for ``api_messages`` (summarize or truncate)."""
    import json

    raw = json.dumps(result, ensure_ascii=False)
    if len(raw) <= cfg.tool_result_max_chars:
        return raw
    if cfg.tool_compression == "summarize":
        sm = cfg.summarization_model or main_model
        try:
            return await summarize_tool_json_with_model(
                model_gateway,
                model=sm,
                raw_json=raw,
                max_out_tokens=512,
            )
        except Exception:
            logger.exception("tool_result_payload_summarize_failed")
            return truncate_tool_json_payload(raw, cfg)
    return truncate_tool_json_payload(raw, cfg)
