"""Adiciona confirmações pendentes de áudio.

Revision ID: 20260919_0003
Revises: 20260918_0002
Create Date: 2026-09-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260919_0003"
down_revision: str | None = "20260918_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_audio_confirmations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "original_whatsapp_message_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column("transcription", sa.Text(), nullable=False),
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
        "ix_pending_audio_confirmations_expires_at",
        "pending_audio_confirmations",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_pending_audio_confirmations_original_whatsapp_message_id",
        "pending_audio_confirmations",
        ["original_whatsapp_message_id"],
        unique=True,
    )
    op.create_index(
        "ix_pending_audio_confirmations_user_id",
        "pending_audio_confirmations",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pending_audio_confirmations_user_id",
        table_name="pending_audio_confirmations",
    )
    op.drop_index(
        "ix_pending_audio_confirmations_original_whatsapp_message_id",
        table_name="pending_audio_confirmations",
    )
    op.drop_index(
        "ix_pending_audio_confirmations_expires_at",
        table_name="pending_audio_confirmations",
    )
    op.drop_table("pending_audio_confirmations")
