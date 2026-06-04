"""Add skills.package_metadata for compiler-facing Skill bundle fields.

Revision ID: 20260508_0006
Revises: 20260508_0005
Create Date: 2026-05-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260508_0006"
down_revision: Union[str, None] = "20260508_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column("package_metadata", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("skills", "package_metadata")
