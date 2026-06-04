"""ORM: session_canvas_states (OpenClaw canvas tool parity)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class SessionCanvasState(Base):
    """Per-session canvas / A2UI state for ui.canvas tool."""

    __tablename__ = "session_canvas_states"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    a2ui_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    eval_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
