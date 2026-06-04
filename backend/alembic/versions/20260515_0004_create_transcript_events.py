"""Create transcript_events table."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260515_0004"
down_revision: str | None = "20260515_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transcript_events",
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_transcript_run_turn",
        "transcript_events",
        ["run_id", "turn_number"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_session",
        "transcript_events",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_event_type",
        "transcript_events",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transcript_event_type", table_name="transcript_events")
    op.drop_index("ix_transcript_session", table_name="transcript_events")
    op.drop_index("ix_transcript_run_turn", table_name="transcript_events")
    op.drop_table("transcript_events")
