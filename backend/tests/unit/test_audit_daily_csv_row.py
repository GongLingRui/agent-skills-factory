"""Daily audit stats CSV row builder."""

from datetime import date
from types import SimpleNamespace

from agent_factory.api.v1.audit import _daily_stats_csv_row


def test_daily_csv_row_basic():
    row = SimpleNamespace(
        stat_date=date(2026, 5, 1),
        agent_id="demo-agent",
        department="legal",
        request_count=10,
        error_count=1,
        token_input=100,
        token_output=50,
        p99_latency_ms=200,
        model_distribution={"qwen": 5},
    )
    cells = _daily_stats_csv_row(row)
    assert cells[0] == "2026-05-01"
    assert cells[1] == "demo-agent"
    assert '"qwen"' in cells[8]


def test_daily_csv_formula_prefix():
    row = SimpleNamespace(
        stat_date=date(2026, 1, 1),
        agent_id="=evil",
        department="d",
        request_count=0,
        error_count=0,
        token_input=0,
        token_output=0,
        p99_latency_ms=None,
        model_distribution=None,
    )
    cells = _daily_stats_csv_row(row)
    assert cells[1] == "'=evil"
