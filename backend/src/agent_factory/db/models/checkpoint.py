"""ORM: checkpoints."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class Checkpoint(Base):
    """Session checkpoint for resume."""

    __tablename__ = "checkpoints"
    __table_args__ = (
        Index(
            "ix_checkpoints_run_turn_ts",
            "run_id",
            "turn_number",
            "timestamp",
        ),
    )

    checkpoint_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[str] = mapped_column(String(64))
    turn_number: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    messages: Mapped[Any | None] = mapped_column(JSONB)
    token_count: Mapped[int | None] = mapped_column(Integer)
    tool_calls_so_far: Mapped[Any | None] = mapped_column(JSONB)
    session_memory: Mapped[str | None] = mapped_column(JSONB)
    last_summarized_message_index: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
