"""Add token usage to assistant run audit records.

Revision ID: 20260917_0003
Revises: 20260917_0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260917_0003"
down_revision: str | None = "20260917_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assistant_runs",
        sa.Column("usage", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("assistant_runs", "usage", server_default=None)


def downgrade() -> None:
    op.drop_column("assistant_runs", "usage")
