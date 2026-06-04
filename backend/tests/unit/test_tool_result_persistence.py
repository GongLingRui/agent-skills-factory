"""Tests for tool_result_persistence helpers."""

from __future__ import annotations

import json

import pytest

from agent_factory.core.context_memory import ContextMemorySettings
from agent_factory.services.tool_result_persistence import (
    is_tool_result_stub,
    make_tool_result_stub,
    parse_tool_result_stub,
    should_persist_tool_result,
)


def test_should_persist_tool_result_true():
    cfg = ContextMemorySettings(
        enabled=True,
        compression="summarize",
        cross_session_memory_enabled=True,
        keep_recent_user_turns=4,
        min_user_turns=1,
        history_budget_chars=96000,
        summary_max_output_tokens=1200,
        summarization_model=None,
        summarize_input_cap_chars=28000,
        max_shrink_rounds=2,
        tool_compression="summarize",
        tool_result_max_chars=8000,
        tool_result_head_chars=2000,
        tool_result_tail_chars=2000,
        chars_per_token_estimate=4,
    )
    assert should_persist_tool_result("x" * 9000, cfg) is True


def test_should_persist_tool_result_false():
    cfg = ContextMemorySettings(
        enabled=True,
        compression="summarize",
        cross_session_memory_enabled=True,
        keep_recent_user_turns=4,
        min_user_turns=1,
        history_budget_chars=96000,
        summary_max_output_tokens=1200,
        summarization_model=None,
        summarize_input_cap_chars=28000,
        max_shrink_rounds=2,
        tool_compression="summarize",
        tool_result_max_chars=8000,
        tool_result_head_chars=2000,
        tool_result_tail_chars=2000,
        chars_per_token_estimate=4,
    )
    assert should_persist_tool_result("small", cfg) is False


def test_make_tool_result_stub():
    stub = make_tool_result_stub(minio_path="bucket/tool_results/r1/1/t1.json", preview="hello")
    obj = json.loads(stub)
    assert obj["_tool_result_stub"] is True
    assert obj["minio_path"] == "bucket/tool_results/r1/1/t1.json"
    assert obj["truncated_preview"] == "hello"


def test_is_tool_result_stub():
    assert is_tool_result_stub('{"_tool_result_stub":true}') is True
    assert is_tool_result_stub('{"foo":1}') is False
    assert is_tool_result_stub(123) is False


def test_parse_tool_result_stub_valid():
    stub = make_tool_result_stub(minio_path="p", preview="x")
    parsed = parse_tool_result_stub(stub)
    assert parsed is not None
    assert parsed["minio_path"] == "p"


def test_parse_tool_result_stub_invalid():
    assert parse_tool_result_stub("not json") is None
    assert parse_tool_result_stub('{}') is None
