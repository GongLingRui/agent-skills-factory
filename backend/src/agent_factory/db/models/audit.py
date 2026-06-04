"""ORM: audit_logs, agent_usage_logs, feedback_logs, daily_stats, security_events."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class AuditLog(Base):
    """Audit log (partitioned by timestamp; mapped to parent table)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[str | None] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    level: Mapped[str | None] = mapped_column(String(16))
    user_id_hash: Mapped[str | None] = mapped_column(String(64))
    agent_id: Mapped[str | None] = mapped_column(String(64))
    department: Mapped[str | None] = mapped_column(String(64))
    tool_calls: Mapped[Any | None] = mapped_column(JSONB)
    token_count: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[float | None] = mapped_column(Float)
    error_code: Mapped[str | None] = mapped_column(String(32))
    retrieval_ids: Mapped[Any | None] = mapped_column(JSONB)
    prompt_summary: Mapped[str | None] = mapped_column(Text)
    retrieval_hits: Mapped[Any | None] = mapped_column(JSONB)
    full_prompt: Mapped[str | None] = mapped_column(Text)
    full_output: Mapped[str | None] = mapped_column(Text)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="active")


class AgentUsageLog(Base):
    """Minimal MAU metadata."""

    __tablename__ = "agent_usage_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id_hash: Mapped[str | None] = mapped_column(String(64))
    salt_version: Mapped[str | None] = mapped_column(String(8))
    agent_id: Mapped[str | None] = mapped_column(String(64))
    # Attribute must not be named ``date`` — shadows ``datetime.date`` in Mapped[].
    usage_date: Mapped[date | None] = mapped_column("date", Date)
    count: Mapped[int] = mapped_column(Integer, default=1)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime)


class FeedbackLog(Base):
    """User thumbs up/down feedback."""

    __tablename__ = "feedback_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64))
    message_id: Mapped[str | None] = mapped_column(String(64))
    run_id: Mapped[str | None] = mapped_column(String(64))
    agent_id: Mapped[str | None] = mapped_column(String(64))
    feedback: Mapped[str | None] = mapped_column(String(16))
    reasons: Mapped[Any | None] = mapped_column(JSONB)
    comment: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)


class DailyStats(Base):
    """Per-day aggregated statistics."""

    __tablename__ = "daily_stats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stat_date: Mapped[date] = mapped_column("date", Date)
    agent_id: Mapped[str] = mapped_column(String(64), default="")
    department: Mapped[str] = mapped_column(String(64), default="")
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    p99_latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_input: Mapped[int] = mapped_column(BigInteger, default=0)
    token_output: Mapped[int] = mapped_column(BigInteger, default=0)
    model_distribution: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)


class SecurityEvent(Base):
    """Security events (prompt injection, etc.)."""

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32))
    user_id_hash: Mapped[str | None] = mapped_column(String(64))
    agent_id: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[str | None] = mapped_column(String(64))
    input_summary: Mapped[str | None] = mapped_column(Text)
    trigger_rule: Mapped[str | None] = mapped_column(String(64))
    queue_priority_before: Mapped[int | None] = mapped_column(Integer)
    queue_priority_after: Mapped[int | None] = mapped_column(Integer)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
