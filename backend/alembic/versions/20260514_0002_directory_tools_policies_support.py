"""Synced directory, tool approval metadata, tool_approval_logs."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260514_0002"
down_revision: str | None = "20260514_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "synced_users",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("department", sa.String(length=64), nullable=True),
        sa.Column(
            "portal_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "synced_departments",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("parent_code", sa.String(length=64), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "user_role_overlays",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("operator_id", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.add_column(
        "tools",
        sa.Column("submitted_by_operator_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tools",
        sa.Column("approved_by_operator_id", sa.String(length=64), nullable=True),
    )
    op.create_table(
        "tool_approval_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tool_id", sa.String(length=64), nullable=False),
        sa.Column("actor_operator_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tool_approval_logs_tool_id",
        "tool_approval_logs",
        ["tool_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tool_approval_logs_tool_id", table_name="tool_approval_logs")
    op.drop_table("tool_approval_logs")
    op.drop_column("tools", "approved_by_operator_id")
    op.drop_column("tools", "submitted_by_operator_id")
    op.drop_table("user_role_overlays")
    op.drop_table("synced_departments")
    op.drop_table("synced_users")
