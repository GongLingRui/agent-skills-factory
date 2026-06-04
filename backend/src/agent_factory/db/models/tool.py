"""ORM: tools."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class Tool(Base):
    """Tool Registry entry."""

    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    input_schema: Mapped[Any | None] = mapped_column(JSONB)
    output_schema: Mapped[Any | None] = mapped_column(JSONB)
    permission_required: Mapped[Any | None] = mapped_column(JSONB)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer)
    rate_limit: Mapped[Any | None] = mapped_column(JSONB)
    implementation: Mapped[Any | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="active")
    submitted_by_operator_id: Mapped[str | None] = mapped_column(String(64))
    approved_by_operator_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
