"""Tests for eval case scoring (docs/04)."""

from __future__ import annotations

from agent_factory.core.eval_scoring import score_case_output


def test_score_empty_when_no_expectations() -> None:
    s, r = score_case_output(text="hello", case={})
    assert s == 1.0
    assert r == []


def test_score_zero_on_empty_output_without_expectations() -> None:
    s, r = score_case_output(text="   ", case={})
    assert s == 0.0
    assert r


def test_schema_fields_all_present() -> None:
    case = {
        "id": "a",
        "name": "n",
        "input": {"message": "x"},
        "min_score": 0.5,
        "expected_schema_fields": ["risk_level", "suggestion"],
    }
    text = '{"risk_level": "low", "suggestion": "ok", "extra": 1}'
    s, r = score_case_output(text=text, case=case)
    assert s == 1.0
    assert r == []


def test_schema_fields_missing() -> None:
    case = {
        "id": "a",
        "name": "n",
        "input": {"message": "x"},
        "min_score": 0.5,
        "expected_schema_fields": ["risk_level"],
    }
    s, r = score_case_output(text='{"suggestion": "ok"}', case=case)
    assert s == 0.0
    assert any("missing schema" in x for x in r)


def test_json_in_markdown_fence() -> None:
    case = {
        "id": "a",
        "name": "n",
        "input": {"message": "x"},
        "min_score": 0.5,
        "expected_schema_fields": ["a"],
    }
    text = """Here is JSON:\n```json\n{"a": 1}\n```"""
    s, r = score_case_output(text=text, case=case)
    assert s == 1.0
    assert r == []


def test_expected_tags() -> None:
    case = {
        "id": "a",
        "name": "n",
        "input": {"message": "x"},
        "min_score": 0.5,
        "expected_tags": ["payment_risk", "high"],
    }
    s, r = score_case_output(
        text="Analysis: payment_risk is HIGH priority.",
        case=case,
    )
    assert s == 1.0


def test_tags_and_schema_min() -> None:
    case = {
        "id": "a",
        "name": "n",
        "input": {"message": "x"},
        "min_score": 0.5,
        "expected_schema_fields": ["x"],
        "expected_tags": ["alpha"],
    }
    s, _ = score_case_output(text='{"x": 1} unrelated text', case=case)
    assert s == 0.0
