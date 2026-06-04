"""Short continuation prompts (e.g. deck HTML segment 2+) and context-safe splits."""

from __future__ import annotations

import re
from typing import Any

_CONTINUE_RE = re.compile(
    r"^(继续|下一段|下一段吧|接着|接着来|continue|next|go\s*on)[\s。!！?？…]*$",
    re.IGNORECASE,
)
_HTML_SEGMENT_RE = re.compile(r"HTML\s*第\s*(\d+)\s*段", re.IGNORECASE)
_TAIL_EXCERPT_CHARS = 1200


def is_short_continue_message(text: str) -> bool:
    """True when the user is asking to resume multi-part output."""
    t = (text or "").strip()
    if not t or len(t) > 32:
        return False
    return bool(_CONTINUE_RE.match(t))


def tail_split_index_preserve_context(messages: list[dict[str, Any]]) -> int:
    """Index to split *messages* so a lone short continue keeps prior assistant."""
    if len(messages) <= 1:
        return 0
    last = messages[-1]
    content = last.get("content")
    if (
        last.get("role") == "user"
        and isinstance(content, str)
        and is_short_continue_message(content)
    ):
        return max(0, len(messages) - 2)
    return len(messages) - 1


def enrich_continue_user_message(
    messages: list[dict[str, Any]],
    raw: str,
) -> str:
    """Augment bare「继续」with deck/segment hints from the last assistant turn."""
    if not is_short_continue_message(raw):
        return raw

    last_assistant: str | None = None
    for row in reversed(messages):
        if row.get("role") != "assistant":
            continue
        content = row.get("content")
        if isinstance(content, str) and content.strip():
            last_assistant = content
            break

    if not last_assistant:
        return (
            f"{raw}\n\n"
            "（系统提示：请按 Skill 工作流从上一段输出末尾续写下一段，"
            "不要重复已输出的 head/CSS，也不要重新询问当前进度。）"
        )

    segment_hint = ""
    seg_match = _HTML_SEGMENT_RE.search(last_assistant)
    if seg_match:
        n = int(seg_match.group(1))
        segment_hint = f"上一段为 HTML 第 {n} 段，请输出第 {n + 1} 段。"
    elif "```html" in last_assistant.lower():
        segment_hint = "上一段已输出 HTML 片段，请接上一段末尾续写下一段。"

    tail = last_assistant[-_TAIL_EXCERPT_CHARS:]
    parts = [
        raw,
        "（系统提示：用户要求续写，不要重新收集进度或重复已输出内容。",
    ]
    if segment_hint:
        parts.append(segment_hint)
    parts.append("上一段输出末尾片段：")
    parts.append(f"```\n{tail}\n```")
    parts.append("）")
    return "\n".join(parts)
