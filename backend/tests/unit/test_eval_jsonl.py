"""Tests for evals/skill_cases.jsonl case schema (docs/04)."""

import pytest

from agent_factory.core.eval_jsonl import validate_eval_case_dict


def test_validate_eval_case_dict_ok():
    err = validate_eval_case_dict(
        {
            "id": "c1",
            "name": "n",
            "input": {"message": "hi"},
            "min_score": 0.5,
        }
    )
    assert err == []


@pytest.mark.parametrize(
    "bad",
    [
        "not a dict",
        {},
        {"id": "", "name": "n", "input": {"message": "m"}, "min_score": 0.1},
        {"id": "i", "name": "", "input": {"message": "m"}, "min_score": 0.1},
        {"id": "i", "name": "n", "input": {}, "min_score": 0.1},
        {"id": "i", "name": "n", "input": {"message": ""}, "min_score": 0.1},
        {"id": "i", "name": "n", "input": {"message": "m"}, "min_score": 2},
    ],
)
def test_validate_eval_case_dict_errors(bad):
    assert validate_eval_case_dict(bad)
