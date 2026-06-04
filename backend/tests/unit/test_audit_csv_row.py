"""CSV export row redaction (aligned with JSON list API)."""

from datetime import UTC, datetime
from types import SimpleNamespace

from agent_factory.api.v1.audit import _audit_log_csv_row


def test_csv_row_minimal_omits_prompt_and_full():
    row = SimpleNamespace(
        id=1,
        run_id="r1",
        session_id="s1",
        timestamp=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
        level="minimal",
        user_id_hash="h",
        agent_id="a",
        department="d",
        tool_calls=[{"tool_id": "kb.search"}],
        token_count=10,
        cost=0.1,
        error_code=None,
        retrieval_ids=["x"],
        prompt_summary="secret",
        full_prompt="fp",
        full_output="fo",
    )
    cells = _audit_log_csv_row(row)
    assert cells[4] == "minimal"
    assert cells[13] == ""  # prompt_summary
    assert cells[14] == ""
    assert cells[15] == ""


def test_csv_row_full_includes_columns():
    row = SimpleNamespace(
        id=2,
        run_id="r2",
        session_id="s2",
        timestamp=datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC),
        level="full",
        user_id_hash="h2",
        agent_id="a2",
        department="d2",
        tool_calls=None,
        token_count=None,
        cost=None,
        error_code="E",
        retrieval_ids=None,
        prompt_summary="p" * 300,
        full_prompt="full in",
        full_output="full out",
    )
    cells = _audit_log_csv_row(row)
    assert len(cells[13]) == 200
    assert cells[14] == "full in"
    assert cells[15] == "full out"


def test_csv_formula_injection_prefix():
    row = SimpleNamespace(
        id=3,
        run_id="=cmd",
        session_id="s",
        timestamp=None,
        level="minimal",
        user_id_hash=None,
        agent_id=None,
        department=None,
        tool_calls=None,
        token_count=None,
        cost=None,
        error_code=None,
        retrieval_ids=None,
        prompt_summary=None,
        full_prompt=None,
        full_output=None,
    )
    cells = _audit_log_csv_row(row)
    assert cells[1] == "'=cmd"
