"""Long-context policy for Agent Runner (docs/08-agent-runner.md §上下文治理).

Checkpoint ``messages`` stay full-fidelity; only the payload sent to the model
is compressed. Default ``compression`` is ``summarize`` (LLM memory card) so
conversation content is not discarded via destructive snip.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextMemorySettings:
    """Tunable limits from ``RunSpec.runtime["context_memory"]``."""

    enabled: bool
    compression: str
    cross_session_memory_enabled: bool
    keep_recent_user_turns: int
    min_user_turns: int
    history_budget_chars: int
    summary_max_output_tokens: int
    summarization_model: str | None
    summarize_input_cap_chars: int
    max_shrink_rounds: int
    tool_compression: str
    tool_result_max_chars: int
    tool_result_head_chars: int
    tool_result_tail_chars: int
    chars_per_token_estimate: int

    @classmethod
    def from_runtime(cls, runtime: dict[str, Any] | None) -> ContextMemorySettings:
        """Parse ``runtime`` JSON; unknown keys ignored."""
        rt = runtime or {}
        raw = rt.get("context_memory")
        m: dict[str, Any] = raw if isinstance(raw, dict) else {}

        def _bool(key: str, default: bool) -> bool:
            v = m.get(key, default)
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                low = v.strip().lower()
                if low in ("true", "1", "yes", "on"):
                    return True
                if low in ("false", "0", "no", "off", ""):
                    return False
            if v in (0, 1):
                return bool(int(v))
            return default

        def _int(key: str, default: int, *, lo: int, hi: int) -> int:
            v = m.get(key, default)
            try:
                n = int(v)
            except (TypeError, ValueError):
                return default
            return max(lo, min(hi, n))

        def _str(key: str, default: str) -> str:
            v = m.get(key, default)
            if isinstance(v, str) and v.strip():
                return v.strip().lower()
            return default

        cpt = _int("chars_per_token_estimate", 4, lo=2, hi=8)
        max_tok = _int("tool_result_max_tokens", 2000, lo=256, hi=32_000)
        head_tok = _int("tool_result_head_tokens", 500, lo=64, hi=16_000)
        tail_tok = _int("tool_result_tail_tokens", 500, lo=64, hi=16_000)

        comp = _str("compression", "summarize")
        if comp not in ("summarize", "snip"):
            comp = "summarize"
        tcomp = _str("tool_compression", "summarize")
        if tcomp not in ("summarize", "truncate"):
            tcomp = "summarize"

        sum_model = m.get("summarization_model")
        if isinstance(sum_model, str) and sum_model.strip():
            sm: str | None = sum_model.strip()
        else:
            sm = None

        return cls(
            enabled=_bool("enabled", True),
            compression=comp,
            cross_session_memory_enabled=_bool(
                "cross_session_memory_enabled", True
            ),
            keep_recent_user_turns=_int(
                "keep_recent_user_turns", 4, lo=1, hi=64
            ),
            min_user_turns=_int("min_user_turns", 1, lo=1, hi=64),
            history_budget_chars=_int(
                "history_budget_chars", 96_000, lo=4096, hi=2_000_000
            ),
            summary_max_output_tokens=_int(
                "summary_max_output_tokens", 1200, lo=128, hi=8000
            ),
            summarization_model=sm,
            summarize_input_cap_chars=_int(
                "summarize_input_cap_chars", 28_000, lo=2000, hi=500_000
            ),
            max_shrink_rounds=_int("max_shrink_rounds", 2, lo=1, hi=8),
            tool_compression=tcomp,
            tool_result_max_chars=max(512, max_tok * cpt),
            tool_result_head_chars=max(64, head_tok * cpt),
            tool_result_tail_chars=max(64, tail_tok * cpt),
            chars_per_token_estimate=cpt,
        )


def approx_tokens_from_text(text: str, *, chars_per_token: int) -> int:
    """Rough token estimate (no tokenizer dependency)."""
    cpt = max(2, int(chars_per_token))
    if not text:
        return 0
    return max(1, len(text) // cpt)


def estimate_messages_chars(messages: list[dict[str, Any]]) -> int:
    """Rough size of user/assistant textual content."""
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            total += len(c)
        elif c is not None:
            total += len(str(c))
    return total


def split_tail_by_user_turns(
    messages: list[dict[str, Any]],
    *,
    keep_user_turns: int,
    min_user_turns: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split into (prefix, tail) where *tail* keeps last user-turn window."""
    out = list(messages)
    user_idx = [i for i, row in enumerate(out) if row.get("role") == "user"]
    keep = max(min_user_turns, keep_user_turns)
    if len(user_idx) <= keep:
        return [], out
    first = user_idx[-keep]
    return out[:first], out[first:]


def apply_history_snip(
    messages: list[dict[str, Any]],
    cfg: ContextMemorySettings,
) -> list[dict[str, Any]]:
    """Drop oldest user/assistant turns (destructive fallback)."""
    if not cfg.enabled or not messages:
        return [copy.copy(m) for m in messages]

    out = [copy.copy(m) for m in messages]
    user_idx = [i for i, m in enumerate(out) if m.get("role") == "user"]
    total = len(user_idx)
    keep = max(cfg.min_user_turns, cfg.keep_recent_user_turns)
    if total <= keep:
        return out

    first = user_idx[-keep]
    dropped_users = total - keep
    if first <= 0:
        return out

    # Preserve API invariants: never split tool_use / tool_result pairs
    from agent_factory.core.message_invariants import (
        adjust_index_to_preserve_invariants,
    )

    first = adjust_index_to_preserve_invariants(out, first)
    # If invariant adjustment pushed first beyond the tail, keep everything
    if first >= len(out):
        return out

    snipped = out[first:]
    if snipped and snipped[0].get("role") == "user":
        note = (
            "[上下文压缩] 更早的 "
            f"{dropped_users} 轮用户发言因长度策略已省略；"
            "以下仅保留最近若干轮。若需引用旧细节，请让用户粘贴或新开话题。\n\n"
        )
        u0 = dict(snipped[0])
        prev = u0.get("content")
        u0["content"] = note + (prev if isinstance(prev, str) else str(prev))
        snipped[0] = u0
    else:
        logger.debug(
            "history_snip_first_not_user",
            extra={"first_role": snipped[0].get("role") if snipped else None},
        )

    logger.info(
        "context_memory_history_snip",
        extra={
            "dropped_prefix_messages": first,
            "dropped_user_turns": dropped_users,
            "kept_user_turns": keep,
        },
    )
    return snipped


def truncate_middle_chars(
    text: str,
    *,
    max_chars: int,
    head_chars: int,
    tail_chars: int,
) -> str:
    """Head + tail with an omission marker (legacy tool path)."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    h = max(0, min(head_chars, max_chars // 2))
    t = max(0, min(tail_chars, max_chars - h - 80))
    if h + t >= len(text):
        return text[:max_chars] + "…"
    mid_omitted = len(text) - h - t
    sep = f"\n…（中间省略约 {mid_omitted} 字符）…\n"
    return text[:h] + sep + text[-t:]


def truncate_tool_json_payload(raw: str, cfg: ContextMemorySettings) -> str:
    """Shorten a tool ``content`` string (usually JSON)."""
    if not cfg.enabled or len(raw) <= cfg.tool_result_max_chars:
        return raw
    return truncate_middle_chars(
        raw,
        max_chars=cfg.tool_result_max_chars,
        head_chars=cfg.tool_result_head_chars,
        tail_chars=cfg.tool_result_tail_chars,
    )


def clamp_tool_results_in_api_messages(
    messages: list[dict[str, Any]],
    cfg: ContextMemorySettings,
) -> None:
    """In-place: clamp ``role == tool`` when ``tool_compression`` is truncate."""
    if not cfg.enabled or cfg.tool_compression != "truncate":
        return
    for m in messages:
        if m.get("role") != "tool":
            continue
        c = m.get("content")
        if not isinstance(c, str):
            continue
        new_c = truncate_tool_json_payload(c, cfg)
        if new_c is not c:
            m["content"] = new_c


def tool_result_content_for_api_sync(
    result: dict[str, Any],
    cfg: ContextMemorySettings,
) -> str:
    """Serialize tool result (truncate path only)."""
    raw = json.dumps(result, ensure_ascii=False)
    return truncate_tool_json_payload(raw, cfg)
