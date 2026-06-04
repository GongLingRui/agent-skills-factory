"""Tests for model output parsing and JSON constraint helper."""

from __future__ import annotations

from agent_factory.core.model_output_parse import (
    extract_json_object_from_text,
    output_matches_json_constraint,
    strip_model_reasoning_markup,
)


def test_strip_reasoning_tags() -> None:
    raw = (
        "<think>\ninternal\n</think>\n"
        "你好"
    )
    assert strip_model_reasoning_markup(raw) == "你好"


def test_extract_json_after_reasoning_and_fence() -> None:
    raw = (
        "<think>x</think>\n"
        '说明如下：\n```json\n{"a": 1}\n```'
    )
    obj = extract_json_object_from_text(raw)
    assert obj == {"a": 1}


def test_output_matches_json_constraint_none_without_schema() -> None:
    assert output_matches_json_constraint("not json", schema_name=None) is None


def test_output_matches_json_constraint_true_plain_json() -> None:
    assert (
        output_matches_json_constraint('{"x": 1}', schema_name="any") is True
    )


def test_output_matches_json_constraint_true_with_noise() -> None:
    text = (
        "<think>t</think>\n"
        '下面是结果：\n```json\n{"status":"ok"}\n```'
    )
    assert output_matches_json_constraint(text, schema_name="demo") is True


def test_output_matches_json_constraint_false() -> None:
    assert (
        output_matches_json_constraint("plain prose only", schema_name="x")
        is False
    )
