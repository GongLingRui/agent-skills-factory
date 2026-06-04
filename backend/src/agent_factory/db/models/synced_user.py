"""ORM: portal IAM snapshot + local role overlay (docs/19)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class SyncedUser(Base):
    """Read-only copy of portal user; roles merged with overlay at read time."""

    __tablename__ = "synced_users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(256))
    department: Mapped[str | None] = mapped_column(String(64))
    portal_roles: Mapped[Any | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)


class UserRoleOverlay(Base):
    """Agent-factory capability overlay; does not replace portal master roles."""

    __tablename__ = "user_role_overlays"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    roles: Mapped[Any] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    operator_id: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
