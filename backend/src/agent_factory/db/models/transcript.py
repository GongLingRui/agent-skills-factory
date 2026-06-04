"""ORM: transcript events for audit and debugging replay."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class TranscriptEvent(Base):
    """Fine-grained event stream for a single run turn."""

    __tablename__ = "transcript_events"
    __table_args__ = (
        Index("ix_transcript_run_turn", "run_id", "turn_number"),
        Index("ix_transcript_session", "session_id"),
        Index("ix_transcript_event_type", "event_type"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[str] = mapped_column(String(64))
    turn_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[Any | None] = mapped_column(JSONB)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
