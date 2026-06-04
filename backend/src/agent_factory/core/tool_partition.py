"""Partition tool calls into concurrency-safe batches."""

from __future__ import annotations

from typing import Any


def partition_tool_calls(
    tool_calls: list[dict[str, Any]],
    tool_gateway: Any,  # ToolGateway
) -> list[list[dict[str, Any]]]:
    """Partition tool calls into concurrent and serial batches.

    Each returned batch is either:
    - A **concurrent** batch (len > 1): every tool in the batch is both
      ``concurrency_safe`` and ``read_only`` according to ``tool_gateway``.
    - A **serial** batch (len == 1): a single tool that may have side effects
      or is not safe to run concurrently with siblings.

    This preserves execution semantics while maximizing throughput for
    read-only / stateless tools (e.g. ``kb.search``, ``doc.extract``).
    """
    if not tool_calls:
        return []

    batches: list[list[dict[str, Any]]] = []
    current_concurrent: list[dict[str, Any]] = []

    for tc in tool_calls:
        func = tc.get("function") or {}
        tool_id = func.get("name", "")
        if (
            tool_gateway.is_concurrency_safe(tool_id)
            and tool_gateway.is_read_only(tool_id)
        ):
            current_concurrent.append(tc)
        else:
            if current_concurrent:
                batches.append(current_concurrent)
                current_concurrent = []
            batches.append([tc])

    if current_concurrent:
        batches.append(current_concurrent)

    return batches
