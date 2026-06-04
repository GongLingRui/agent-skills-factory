"""Tests for short continuation message helpers."""

from agent_factory.core.conversation_continue import (
    enrich_continue_user_message,
    is_short_continue_message,
    tail_split_index_preserve_context,
)


def test_is_short_continue_message() -> None:
    assert is_short_continue_message("继续")
    assert is_short_continue_message("Continue!")
    assert not is_short_continue_message("请继续帮我写第三页的内容和配色")
    assert not is_short_continue_message("")


def test_tail_split_keeps_assistant_before_continue() -> None:
    msgs = [
        {"role": "user", "content": "做一份路演"},
        {"role": "assistant", "content": "```html\n" + "x" * 5000},
        {"role": "user", "content": "继续"},
    ]
    assert tail_split_index_preserve_context(msgs) == 1


def test_enrich_continue_includes_segment_and_tail() -> None:
    msgs = [
        {"role": "assistant", "content": "📋 HTML 第 1 段已输出\n```html\n<body>P1</body>"},
    ]
    out = enrich_continue_user_message(msgs, "继续")
    assert "第 2 段" in out
    assert "P1" in out
    assert "不要重新收集进度" in out
