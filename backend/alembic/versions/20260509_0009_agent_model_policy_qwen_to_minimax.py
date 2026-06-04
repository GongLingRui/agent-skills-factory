"""Replace qwen3-* model_policy with MiniMax for environments without local vLLM.

Revision ID: 20260509_0009
Revises: 20260509_0008
Create Date: 2026-05-09
"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20260509_0009"
down_revision: str | None = "20260509_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COND = """
    model_policy IS NOT NULL
    AND (
        (model_policy ? 'default' AND model_policy->>'default' LIKE 'qwen3-%')
        OR (model_policy ? 'fallback' AND model_policy->>'fallback' LIKE 'qwen3-%')
    )
"""


def upgrade() -> None:
    """Agents seeded with localhost qwen endpoints break chat without vLLM."""
    json_literal = '{"default": "MiniMax-M2.7", "fallback": "MiniMax-M2.7"}'
    op.execute(
        text(
            f"""
            UPDATE agent_apps
            SET model_policy = '{json_literal}'::jsonb
            WHERE {_COND}
            """
        )
    )
    op.execute(
        text(
            f"""
            UPDATE agent_versions
            SET model_policy = '{json_literal}'::jsonb
            WHERE {_COND}
            """
        )
    )


def downgrade() -> None:
    """Cannot restore prior JSON without storing old values."""
