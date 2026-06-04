"""ORM: subagent_runs (OpenClaw subagent-registry parity)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class SubagentRun(Base):
    """Tracks spawned sub-agent / sub-session runs."""

    __tablename__ = "subagent_runs"
    __table_args__ = (
        Index("ix_subagent_runs_controller", "controller_session_id"),
        Index("ix_subagent_runs_child", "child_session_id"),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    controller_session_id: Mapped[str] = mapped_column(String(64))
    child_session_id: Mapped[str] = mapped_column(String(64))
    agent_id: Mapped[str] = mapped_column(String(64))
    user_id_hash: Mapped[str] = mapped_column(String(64))
    task_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    yield_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
