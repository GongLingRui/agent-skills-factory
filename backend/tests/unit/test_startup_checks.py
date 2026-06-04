"""Tests for startup dependency checks."""

from __future__ import annotations

from agent_factory.services.startup_checks import is_connection_refused_error


def test_is_connection_refused_error_direct():
    assert is_connection_refused_error(ConnectionRefusedError(61, "refused"))


def test_is_connection_refused_error_wrapped():
    try:
        raise ConnectionRefusedError(61, "refused")
    except ConnectionRefusedError as exc:
        outer = RuntimeError("db failed")
        outer.__cause__ = exc
        assert is_connection_refused_error(outer)


def test_is_connection_refused_error_group():
    inner = ConnectionRefusedError(61, "refused")
    group = ExceptionGroup("task failed", [inner])
    assert is_connection_refused_error(group)
