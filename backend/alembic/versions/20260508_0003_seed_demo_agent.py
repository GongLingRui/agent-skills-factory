"""Seed a demo Agent for local / contract smoke tests.

Revision ID: 20260508_0003
Revises: 20260508_0002
Create Date: 2026-05-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_0003"
down_revision: Union[str, None] = "20260508_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO agent_apps (
                id, name, description, version, owner, lifecycle_state,
                tags, ui_config
            ) VALUES (
                'demo-agent',
                'Demo Agent',
                'Local smoke / portal exchange target',
                '0.1.0',
                'system',
                'active',
                '["演示"]'::jsonb,
                '{"title": "Demo Agent", "welcome_message": "Hello"}'::jsonb
            )
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM agent_apps WHERE id = 'demo-agent'"))
