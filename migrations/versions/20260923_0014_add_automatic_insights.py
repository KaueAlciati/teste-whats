"""Adiciona preferência e invalidação de insights automáticos.

Revision ID: 20260923_0014
Revises: 20260923_0013
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260923_0014"
down_revision: str | None = "20260923_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "automatic_insights_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "financial_profiles",
        sa.Column(
            "analysis_stale",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("financial_profiles", "analysis_stale")
    op.drop_column("users", "automatic_insights_enabled")
