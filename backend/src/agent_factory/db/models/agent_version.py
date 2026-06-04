"""ORM: agent_versions."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class AgentVersion(Base):
    """Agent version history for rollback / audit."""

    __tablename__ = "agent_versions"

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    instruction: Mapped[str | None] = mapped_column(Text)
    release_config: Mapped[Any | None] = mapped_column(JSONB)
    model_policy: Mapped[Any | None] = mapped_column(JSONB)
    skill_config: Mapped[Any | None] = mapped_column(JSONB)
    tools_allow: Mapped[Any | None] = mapped_column(JSONB)
    knowledge_scopes: Mapped[Any | None] = mapped_column(JSONB)
    output_schema: Mapped[str | None] = mapped_column(String(64))
    limits_config: Mapped[Any | None] = mapped_column(JSONB)
    concurrency_config: Mapped[Any | None] = mapped_column(JSONB)
    audit_config: Mapped[Any | None] = mapped_column(JSONB)
    enterprise_config: Mapped[Any | None] = mapped_column(JSONB)
    tags: Mapped[Any | None] = mapped_column(JSONB)
    ui_config: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str | None] = mapped_column(String(64))
