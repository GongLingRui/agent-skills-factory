"""Repair missing tool results in message sequences."""

from __future__ import annotations

from typing import Any


def repair_missing_tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every assistant message with tool_calls has matching tool messages.

    If the last assistant message contains tool_calls but no subsequent tool
    messages exist, insert compensation tool messages for each missing call.
    """
    if not messages:
        return messages

    out = list(messages)
    last = out[-1]
    if last.get("role") != "assistant":
        return out

    tool_calls = last.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        return out

    # Count existing tool messages after this assistant message
    # Since last is the final message, there are zero tool messages after it.
    existing_tool_ids = set()
    for m in out:
        if m.get("role") == "tool":
            tcid = m.get("tool_call_id")
            if tcid:
                existing_tool_ids.add(tcid)

    needed = [tc for tc in tool_calls if tc.get("id") not in existing_tool_ids]
    if not needed:
        return out

    for tc in needed:
        out.append(
            {
                "role": "tool",
                "tool_call_id": str(tc.get("id") or ""),
                "content": "[工具结果缺失：执行中断，无返回值]",
            }
        )
    return out
