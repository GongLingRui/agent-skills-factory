"""ORM: sessions (browser + chat lifecycle)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class ChatSession(Base):
    """Cookie-bound session; run_id/agent_id filled after POST .../init."""

    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("run_specs.run_id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id_hash: Mapped[str] = mapped_column(String(64))
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="created")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_activity: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    allowed_agents: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    data_domains: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    permissions: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    revoke_gen_seen: Mapped[int] = mapped_column(Integer, default=0)
    runtime_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    session_kind: Mapped[str] = mapped_column(String(16), default="main")
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parent_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    controller_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
