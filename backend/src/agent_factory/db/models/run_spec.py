"""ORM: run_specs."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class RunSpec(Base):
    """Compiled run specification (immutable)."""

    __tablename__ = "run_specs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    runspec_schema_version: Mapped[int | None] = mapped_column(Integer)
    agent_id: Mapped[str | None] = mapped_column(String(64))
    agent_version: Mapped[str | None] = mapped_column(String(32))
    skill_id: Mapped[str | None] = mapped_column(String(64))
    skill_version: Mapped[str | None] = mapped_column(String(32))
    skill_package_hash: Mapped[str | None] = mapped_column(String(64))
    skill_file_manifest: Mapped[Any | None] = mapped_column(JSONB)
    user_id_hash: Mapped[str] = mapped_column(String(64))
    department: Mapped[str | None] = mapped_column(String(64))
    prompt_parts: Mapped[Any | None] = mapped_column(JSONB)
    lazy_references: Mapped[Any | None] = mapped_column(JSONB)
    indexed_references: Mapped[Any | None] = mapped_column(JSONB)
    allowed_tools: Mapped[Any | None] = mapped_column(JSONB)
    retrieval_scopes: Mapped[Any | None] = mapped_column(JSONB)
    script_hooks: Mapped[Any | None] = mapped_column(JSONB)
    output_schema: Mapped[str | None] = mapped_column(String(64))
    runtime: Mapped[Any | None] = mapped_column(JSONB)
    audit: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
