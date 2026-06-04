"""Tests for JSON Schema output validation."""

from __future__ import annotations

from agent_factory.core.output_schema_validator import (
    output_matches_schema_constraint,
    validate_json_against_schema,
)


def test_validate_json_against_schema_required_field():
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
    }
    ok, errs = validate_json_against_schema({"status": "ok"}, schema)
    assert ok is True
    assert errs == []
    bad, errs2 = validate_json_against_schema({}, schema)
    assert bad is False
    assert errs2


def test_output_matches_schema_constraint_with_metadata():
    meta = {
        "schema_files": {
            "demo-report": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
            }
        }
    }
    good = '{"answer": "yes"}'
    assert (
        output_matches_schema_constraint(
            good,
            schema_name="demo-report",
            package_metadata=meta,
        )
        is True
    )
    bad = '{"wrong": 1}'
    assert (
        output_matches_schema_constraint(
            bad,
            schema_name="demo-report",
            package_metadata=meta,
        )
        is False
    )
