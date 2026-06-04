"""Runner token usage warning helper (prd.md §7.5)."""

from agent_factory.services import runner_service as rs


def test_usage_warning_when_near_cap():
    msg = rs._usage_warning_message(
        {"total_tokens": 9000},
        max_tokens=10000,
    )
    assert msg
    assert "上限" in msg


def test_usage_warning_uses_prompt_plus_completion():
    msg = rs._usage_warning_message(
        {"prompt_tokens": 8000, "completion_tokens": 900},
        max_tokens=10000,
    )
    assert msg


def test_usage_warning_none_when_low():
    assert rs._usage_warning_message({"total_tokens": 100}, max_tokens=10000) is None
    assert rs._usage_warning_message(None, max_tokens=8000) is None
