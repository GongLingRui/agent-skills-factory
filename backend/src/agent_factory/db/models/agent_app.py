"""ORM: agent_apps (registry)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class AgentApp(Base):
    """Declarative mapping aligned with docs/17 `agent_apps`."""

    __tablename__ = "agent_apps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    instruction: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(32))
    runspec_schema_version: Mapped[int] = mapped_column(Integer, default=1)
    owner: Mapped[str | None] = mapped_column(String(64))
    lifecycle_state: Mapped[str] = mapped_column(String(16), default="active")
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
    degradation_exempt: Mapped[bool] = mapped_column(default=False)
    cold_since: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[str | None] = mapped_column(String(64))
