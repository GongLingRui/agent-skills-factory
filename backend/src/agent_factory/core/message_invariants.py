"""Preserve API invariants when compacting / snipping messages.

The OpenAI Chat Completions API (and compatible providers) require that
``tool_use`` assistant messages be immediately followed by their matching
``tool`` messages.  Cutting a message list in the middle of a tool pair
produces a 400 error from the provider.
"""

from __future__ import annotations

from typing import Any


def adjust_index_to_preserve_invariants(
    messages: list[dict[str, Any]],
    cut_index: int,
) -> int:
    """Adjust *cut_index* so that dropping ``messages[0:cut_index]`` never
    splits an assistant ``tool_calls`` / ``tool`` result pair.

    If *cut_index* falls between an assistant message that issued tool calls
    and the corresponding tool result messages, the index is moved **forward**
    to the end of the tool result block so the entire pair is dropped together.

    Returns the (possibly unchanged) cut_index.
    """
    if cut_index <= 0 or cut_index >= len(messages):
        return cut_index

    # Collect tool_call ids from assistant messages that would be DROPPED
    dropped_assistant_tc_ids: set[str] = set()
    for i in range(cut_index):
        m = messages[i]
        if m.get("role") == "assistant":
            tcs = m.get("tool_calls")
            if isinstance(tcs, list):
                for tc in tcs:
                    tcid = tc.get("id")
                    if isinstance(tcid, str):
                        dropped_assistant_tc_ids.add(tcid)

    # Remove ids whose tool results are ALSO dropped (complete pair)
    for i in range(cut_index):
        m = messages[i]
        if m.get("role") == "tool":
            tcid = m.get("tool_call_id")
            if tcid in dropped_assistant_tc_ids:
                dropped_assistant_tc_ids.discard(tcid)

    # If no dangling ids, the cut is safe
    if not dropped_assistant_tc_ids:
        return cut_index

    # Move cut_index forward past all tool results belonging to the
    # dropped assistant messages (drop the incomplete block entirely).
    new_index = cut_index
    for i in range(cut_index, len(messages)):
        m = messages[i]
        if m.get("role") == "tool":
            tcid = m.get("tool_call_id")
            if tcid in dropped_assistant_tc_ids:
                new_index = i + 1
            else:
                # End of contiguous tool block
                break
        else:
            break

    return min(new_index, len(messages))
