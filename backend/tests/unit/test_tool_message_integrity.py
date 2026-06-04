"""Tests for tool_message_integrity repair."""

from __future__ import annotations

from agent_factory.core.tool_message_integrity import repair_missing_tool_results


def test_no_repair_needed():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    out = repair_missing_tool_results(msgs)
    assert out == msgs


def test_repair_missing_tool_results():
    msgs = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "function": {"name": "kb.search"}},
                {"id": "call_2", "function": {"name": "doc.extract"}},
            ],
        },
    ]
    out = repair_missing_tool_results(msgs)
    assert len(out) == 4
    assert out[2]["role"] == "tool"
    assert out[2]["tool_call_id"] == "call_1"
    assert out[3]["role"] == "tool"
    assert out[3]["tool_call_id"] == "call_2"
    assert "缺失" in out[2]["content"]


def test_no_repair_when_tool_messages_exist():
    msgs = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_1", "function": {"name": "kb.search"}}],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "result"},
    ]
    out = repair_missing_tool_results(msgs)
    assert len(out) == 3
