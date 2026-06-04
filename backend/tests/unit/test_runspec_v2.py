"""Tests for RunSpec v2 runtime overrides."""

from __future__ import annotations

from agent_factory.core.runspec_v2 import (
    apply_v2_runtime_overrides,
    v2_requires_strict_schema_validation,
)


def test_v1_unchanged():
    rt = {"max_turns": 6, "model": "m"}
    out = apply_v2_runtime_overrides(rt, runspec_schema_version=1)
    assert out == rt
    assert "runspec_v2_semantics" not in out


def test_v2_adds_context_memory_and_cap():
    rt = {"max_turns": 20}
    out = apply_v2_runtime_overrides(rt, runspec_schema_version=2)
    assert out["max_turns"] == 12
    assert out["runspec_v2_semantics"] is True
    assert "context_memory" in out


def test_v2_strict_schema_flag():
    assert v2_requires_strict_schema_validation(2) is True
    assert v2_requires_strict_schema_validation(1) is False
