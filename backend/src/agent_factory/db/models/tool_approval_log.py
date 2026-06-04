"""ORM: Tool Registry dual-sign audit trail."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class ToolApprovalLog(Base):
    """Who approved / submitted a tool change."""

    __tablename__ = "tool_approval_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tool_id: Mapped[str] = mapped_column(String(64))
    actor_operator_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
