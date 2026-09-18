"""Adiciona confirmações pendentes de comprovantes.

Revision ID: 20260918_0002
Revises: 20260918_0001
Create Date: 2026-09-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260918_0002"
down_revision: str | None = "20260918_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("whatsapp_message_id", sa.String(length=255), nullable=False),
        sa.Column(
            "extracted_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pending_receipts_expires_at",
        "pending_receipts",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_pending_receipts_user_id",
        "pending_receipts",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_pending_receipts_whatsapp_message_id",
        "pending_receipts",
        ["whatsapp_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pending_receipts_whatsapp_message_id",
        table_name="pending_receipts",
    )
    op.drop_index("ix_pending_receipts_user_id", table_name="pending_receipts")
    op.drop_index("ix_pending_receipts_expires_at", table_name="pending_receipts")
    op.drop_table("pending_receipts")
