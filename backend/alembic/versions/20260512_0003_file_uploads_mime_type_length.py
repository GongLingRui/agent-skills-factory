"""Widen file_uploads.mime_type for Office Open XML MIME strings.

Revision ID: 20260512_0003
Revises: 20260512_0002
Create Date: 2026-05-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260512_0003"
down_revision: str | None = "20260512_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE file_uploads "
        "ALTER COLUMN mime_type TYPE VARCHAR(255)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE file_uploads "
        "ALTER COLUMN mime_type TYPE VARCHAR(64) "
        "USING left(mime_type, 64)"
    )
