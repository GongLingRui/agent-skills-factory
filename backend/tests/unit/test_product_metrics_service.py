"""Product metrics aggregation (services/product_metrics)."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_factory.services.product_metrics import (
    compute_product_metrics_summary,
)


@pytest.mark.asyncio
async def test_compute_product_metrics_executes_expected_queries():
    """Smoke coverage for SELECT wiring (values come from mocked rows)."""
    db = AsyncMock()

    def _exec(stmt):
        sql = str(stmt)
        m = MagicMock()
        if "agent_usage_logs" in sql and "GROUP BY" in sql:
            m.all.return_value = []
        elif "agent_usage_logs" in sql and "count(distinct" in sql.lower():
            m.scalar_one.return_value = 0
        elif "sessions" in sql and "count" in sql.lower():
            m.scalar_one.return_value = 0
        elif "agent_apps" in sql:
            m.scalar_one.return_value = 0
        elif "feedback_logs" in sql:
            m.all.return_value = []
        else:
            m.scalar_one.return_value = 0
            m.all.return_value = []
        return m

    db.execute = AsyncMock(side_effect=_exec)

    out = await compute_product_metrics_summary(
        db,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 7),
        mau_window_days=30,
    )

    assert out["start_date"] == "2026-05-01"
    assert out["end_date"] == "2026-05-07"
    assert out["dau_by_day"] == []
    assert out["feedback"]["total"] == 0
    assert db.execute.await_count >= 5
