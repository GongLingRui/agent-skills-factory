"""ORM: degradation_events, config_change_logs, daily_feedback_stats,
archive_manifests, system_configs.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class DegradationEvent(Base):
    """Global degradation event log."""

    __tablename__ = "degradation_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    level: Mapped[int] = mapped_column(Integer)
    previous_level: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)
    operator_id: Mapped[str | None] = mapped_column(String(64))
    metrics_snapshot: Mapped[Any | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime)
    expected_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)


class ConfigChangeLog(Base):
    """Config audit trail."""

    __tablename__ = "config_change_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_name: Mapped[str] = mapped_column(String(64))
    record_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))
    old_value: Mapped[Any | None] = mapped_column(JSONB)
    new_value: Mapped[Any | None] = mapped_column(JSONB)
    change_reason: Mapped[str | None] = mapped_column(Text)
    operator_id: Mapped[str] = mapped_column(String(64))
    operator_ip: Mapped[str | None] = mapped_column(String(64))
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)


class DailyFeedbackStats(Base):
    """Aggregated feedback stats per agent per day."""

    __tablename__ = "daily_feedback_stats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stat_date: Mapped[date] = mapped_column("date", Date)
    agent_id: Mapped[str] = mapped_column(String(64))
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    feedback_up: Mapped[int] = mapped_column(Integer, default=0)
    feedback_down: Mapped[int] = mapped_column(Integer, default=0)
    feedback_rate: Mapped[float] = mapped_column(default=0)
    reason_distribution: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)


class ArchiveManifest(Base):
    """Archive job manifest."""

    __tablename__ = "archive_manifests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    archive_type: Mapped[str] = mapped_column(String(32))
    file_path: Mapped[str] = mapped_column(String(512))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    record_count: Mapped[int | None] = mapped_column(BigInteger)
    date_range_start: Mapped[date] = mapped_column(Date)
    date_range_end: Mapped[date] = mapped_column(Date)
    checksum_md5: Mapped[str | None] = mapped_column(String(32))
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    archived_at: Mapped[datetime] = mapped_column(DateTime)
    archived_by: Mapped[str | None] = mapped_column(String(64))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)


class SystemConfig(Base):
    """Key-value system configuration."""

    __tablename__ = "system_configs"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_by: Mapped[str | None] = mapped_column(String(64))
