"""ORM: department tree snapshot from portal IAM."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class SyncedDepartment(Base):
    """Department node (flat + parent link for tree reconstruction)."""

    __tablename__ = "synced_departments"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    parent_code: Mapped[str | None] = mapped_column(String(64))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)
