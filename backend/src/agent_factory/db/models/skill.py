"""ORM: skills."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class Skill(Base):
    """Skill Package registry (composite PK id+version)."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    when_to_use: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(64))
    risk_tier: Mapped[str | None] = mapped_column(String(16))
    skill_package_hash: Mapped[str | None] = mapped_column(String(64))
    package_metadata: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    activation_conditions: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="active")
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime)
    deprecated_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str | None] = mapped_column(String(64))
