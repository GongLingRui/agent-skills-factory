"""Add agent_apps.instruction; seed demo Skill + wire demo-agent.

Revision ID: 20260508_0004
Revises: 20260508_0003
Create Date: 2026-05-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_0004"
down_revision: Union[str, None] = "20260508_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_apps",
        sa.Column("instruction", sa.Text(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO skills (
                id, version, name, description, when_to_use,
                risk_tier, skill_package_hash, status
            ) VALUES (
                'demo-skill',
                '0.1.0',
                'Demo Skill',
                'Smoke / local testing skill',
                'Follow user instructions briefly.',
                'low',
                'deadbeef0000',
                'active'
            )
            ON CONFLICT (id, version) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE agent_apps SET
                instruction = '你是 Demo Agent，用于本地联调；回答简洁。',
                skill_config = '{"id":"demo-skill","version_pin":"0.1.0"}'::jsonb,
                release_config = '{"strategy":"full"}'::jsonb
            WHERE id = 'demo-agent'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("agent_apps", "instruction")
