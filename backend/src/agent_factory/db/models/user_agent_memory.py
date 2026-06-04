"""ORM: per-user per-agent cross-session summary (rolling memory card)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class UserAgentMemory(Base):
    """Server-side rolling summary for continuity across chat sessions."""

    __tablename__ = "user_agent_memory"

    user_id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    summary_text: Mapped[str] = mapped_column(Text, default="")
    segments: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
