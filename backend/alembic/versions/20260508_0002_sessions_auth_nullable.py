"""Allow sessions before RunSpec init (cookie session without run_id).

Revision ID: 20260508_0002
Revises: 20260508_0001
Create Date: 2026-05-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_0002"
down_revision: Union[str, None] = "20260508_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sessions",
        "run_id",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.alter_column(
        "sessions",
        "agent_id",
        existing_type=sa.String(length=64),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM sessions WHERE run_id IS NULL OR agent_id IS NULL")
    )
    op.alter_column(
        "sessions",
        "run_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "sessions",
        "agent_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
