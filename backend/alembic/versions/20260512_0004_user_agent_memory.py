"""Cross-session user+agent summary memory.

Revision ID: 20260512_0004
Revises: 20260512_0003
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260512_0004"
down_revision: str | None = "20260512_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_agent_memory",
        sa.Column("user_id_hash", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_run_id", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("user_id_hash", "agent_id"),
    )


def downgrade() -> None:
    op.drop_table("user_agent_memory")
