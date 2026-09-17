"""Add logical section metadata to documents.

Revision ID: 20260917_0004
Revises: 20260917_0003
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260917_0004"
down_revision: str | None = "20260917_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("sections", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("documents", "sections", server_default=None)


def downgrade() -> None:
    op.drop_column("documents", "sections")
