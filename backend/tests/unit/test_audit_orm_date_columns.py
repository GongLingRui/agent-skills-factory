"""Regression: DB column ``date`` must map to non-reserved Python attrs.

Using ORM attribute name ``date`` with ``Mapped[date | None]`` breaks SQLAlchemy
typing scan on Python 3.13 (``date`` shadows ``datetime.date`` in annotations).
"""

from agent_factory.db.models.audit import AgentUsageLog, DailyStats


def test_agent_usage_logs_column_date_mapped_to_usage_date():
    assert "date" in AgentUsageLog.__table__.c
    assert "usage_date" in AgentUsageLog.__mapper__.attrs


def test_daily_stats_column_date_mapped_to_stat_date():
    assert "date" in DailyStats.__table__.c
    assert "stat_date" in DailyStats.__mapper__.attrs
