"""Unit tests for long-context / memory policy (docs/08)."""

from dataclasses import replace

from agent_factory.core.context_memory import (
    ContextMemorySettings,
    apply_history_snip,
    approx_tokens_from_text,
    estimate_messages_chars,
    split_tail_by_user_turns,
    truncate_middle_chars,
    truncate_tool_json_payload,
)


def _cfg(**overrides: object) -> ContextMemorySettings:
    base = ContextMemorySettings.from_runtime({})
    return replace(base, **overrides)  # type: ignore[arg-type]


def test_defaults_use_summarize_compression() -> None:
    s = ContextMemorySettings.from_runtime({})
    assert s.compression == "summarize"
    assert s.tool_compression == "summarize"


def test_approx_tokens() -> None:
    assert approx_tokens_from_text("abcd", chars_per_token=2) == 2
    assert approx_tokens_from_text("", chars_per_token=4) == 0


def test_truncate_middle_chars() -> None:
    s = "a" * 100
    out = truncate_middle_chars(s, max_chars=40, head_chars=8, tail_chars=8)
    assert out.startswith("aaaaaaaa")
    assert out.endswith("aaaaaaaa")
    assert "省略" in out


def test_split_tail_by_user_turns() -> None:
    msgs = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    pre, tail = split_tail_by_user_turns(
        msgs, keep_user_turns=1, min_user_turns=1
    )
    assert len(pre) == 2
    assert len(tail) == 1
    assert tail[0]["content"] == "u2"


def test_apply_history_snip_keeps_last_two_user_turns() -> None:
    cfg = _cfg(keep_recent_user_turns=2, min_user_turns=1, compression="snip")
    msgs = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
    ]
    out = apply_history_snip(msgs, cfg)
    assert len(out) == 4
    assert out[0]["role"] == "user"
    assert "u2" in out[0]["content"]
    assert "上下文压缩" in out[0]["content"]
    assert out[1]["content"] == "a2"


def test_apply_history_snip_disabled_returns_copy_shape() -> None:
    cfg = _cfg(enabled=False)
    msgs = [{"role": "user", "content": "x"}]
    out = apply_history_snip(msgs, cfg)
    assert len(out) == 1
    assert out[0]["content"] == "x"


def test_context_memory_from_runtime_overrides() -> None:
    s = ContextMemorySettings.from_runtime(
        {
            "context_memory": {
                "keep_recent_user_turns": 2,
                "tool_result_max_tokens": 1000,
                "tool_result_head_tokens": 100,
                "tool_result_tail_tokens": 100,
                "chars_per_token_estimate": 4,
                "compression": "snip",
            },
        },
    )
    assert s.keep_recent_user_turns == 2
    assert s.tool_result_max_chars == 4000
    assert s.compression == "snip"


def test_truncate_tool_json_payload() -> None:
    cfg = _cfg(
        tool_result_max_chars=120,
        tool_result_head_chars=20,
        tool_result_tail_chars=20,
        tool_compression="truncate",
    )
    big = {"text": "x" * 500}
    import json

    raw = json.dumps(big, ensure_ascii=False)
    out = truncate_tool_json_payload(raw, cfg)
    assert len(out) < 400
    assert out.startswith('{"text": "xxxx')
    assert "省略" in out


def test_estimate_messages_chars() -> None:
    m = [
        {"role": "user", "content": "ab"},
        {"role": "assistant", "content": "c"},
    ]
    assert estimate_messages_chars(m) == 3
