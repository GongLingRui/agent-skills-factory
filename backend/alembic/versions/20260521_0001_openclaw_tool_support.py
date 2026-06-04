"""OpenClaw tool support: session metadata, subagent runs, cron, canvas."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260521_0001"
down_revision: str | None = "20260515_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("session_kind", sa.String(16), server_default="main", nullable=False),
    )
    op.add_column("sessions", sa.Column("label", sa.String(256), nullable=True))
    op.add_column("sessions", sa.Column("title", sa.String(512), nullable=True))
    op.add_column("sessions", sa.Column("parent_session_id", sa.String(64), nullable=True))
    op.add_column(
        "sessions",
        sa.Column("controller_session_id", sa.String(64), nullable=True),
    )
    op.add_column("sessions", sa.Column("run_status", sa.String(16), nullable=True))
    op.create_index("ix_sessions_user_agent", "sessions", ["user_id_hash", "agent_id"])
    op.create_index("ix_sessions_parent", "sessions", ["parent_session_id"])

    op.create_table(
        "subagent_runs",
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("controller_session_id", sa.String(64), nullable=False),
        sa.Column("child_session_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("user_id_hash", sa.String(64), nullable=False),
        sa.Column("task_name", sa.String(128), nullable=True),
        sa.Column("label", sa.String(256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("yield_message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_subagent_runs_controller",
        "subagent_runs",
        ["controller_session_id"],
    )
    op.create_index(
        "ix_subagent_runs_child",
        "subagent_runs",
        ["child_session_id"],
    )

    op.create_table(
        "agent_cron_jobs",
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("user_id_hash", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("delivery", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("delete_after_run", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index("ix_agent_cron_jobs_next_run", "agent_cron_jobs", ["next_run_at"])

    op.create_table(
        "session_canvas_states",
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("visible", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("a2ui_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("eval_result", sa.Text(), nullable=True),
        sa.Column("snapshot_base64", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("session_id"),
    )


def downgrade() -> None:
    op.drop_table("session_canvas_states")
    op.drop_index("ix_agent_cron_jobs_next_run", table_name="agent_cron_jobs")
    op.drop_table("agent_cron_jobs")
    op.drop_index("ix_subagent_runs_child", table_name="subagent_runs")
    op.drop_index("ix_subagent_runs_controller", table_name="subagent_runs")
    op.drop_table("subagent_runs")
    op.drop_index("ix_sessions_parent", table_name="sessions")
    op.drop_index("ix_sessions_user_agent", table_name="sessions")
    op.drop_column("sessions", "run_status")
    op.drop_column("sessions", "controller_session_id")
    op.drop_column("sessions", "parent_session_id")
    op.drop_column("sessions", "title")
    op.drop_column("sessions", "label")
    op.drop_column("sessions", "session_kind")
