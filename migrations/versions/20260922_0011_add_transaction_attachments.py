"""Adiciona anexos vinculados às transações.

Revision ID: 20260922_0011
Revises: 20260922_0010
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260922_0011"
down_revision: str | None = "20260922_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transaction_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mime_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name="ck_transaction_attachments_mime_type",
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name="ck_transaction_attachments_size_bytes",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["financial_transactions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transaction_id",
            "storage_key",
            name="uq_transaction_attachments_transaction_storage",
        ),
    )
    op.create_index(
        "ix_transaction_attachments_sha256",
        "transaction_attachments",
        ["sha256"],
    )
    op.create_index(
        "ix_transaction_attachments_storage_key",
        "transaction_attachments",
        ["storage_key"],
    )
    op.create_index(
        "ix_transaction_attachments_transaction_id",
        "transaction_attachments",
        ["transaction_id"],
    )
    op.create_index(
        "ix_transaction_attachments_user_id",
        "transaction_attachments",
        ["user_id"],
    )
    op.create_index(
        "ix_transaction_attachments_user_transaction",
        "transaction_attachments",
        ["user_id", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transaction_attachments_user_transaction",
        table_name="transaction_attachments",
    )
    op.drop_index(
        "ix_transaction_attachments_user_id",
        table_name="transaction_attachments",
    )
    op.drop_index(
        "ix_transaction_attachments_transaction_id",
        table_name="transaction_attachments",
    )
    op.drop_index(
        "ix_transaction_attachments_storage_key",
        table_name="transaction_attachments",
    )
    op.drop_index(
        "ix_transaction_attachments_sha256",
        table_name="transaction_attachments",
    )
    op.drop_table("transaction_attachments")
