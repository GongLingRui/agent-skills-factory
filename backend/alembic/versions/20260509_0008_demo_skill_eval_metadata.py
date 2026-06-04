"""Seed demo-skill package_metadata.eval_cases for SKILL_EVAL_CASES_REQUIRED.

Revision ID: 20260509_0008
Revises: 20260508_0007
Create Date: 2026-05-09
"""

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

revision: str = "20260509_0008"
down_revision: str | None = "20260508_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_META = (
    '{"eval_cases": ['
    '{"id": "demo-smoke", "name": "demo smoke", '
    '"input": {"message": "hello"}, "min_score": 0.0}'
    "]}"
)


def upgrade() -> None:
    op.execute(
        text(
            """
            UPDATE skills
            SET package_metadata = CAST(:meta AS jsonb)
            WHERE id = 'demo-skill' AND version = '0.1.0'
            """
        ).bindparams(meta=_META)
    )


def downgrade() -> None:
    op.execute(
        text(
            """
            UPDATE skills
            SET package_metadata = NULL
            WHERE id = 'demo-skill' AND version = '0.1.0'
            """
        )
    )
