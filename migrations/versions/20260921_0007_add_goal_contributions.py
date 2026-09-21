"""Adiciona histórico de aportes e contexto de meta selecionada.

Revision ID: 20260921_0007
Revises: 20260921_0006
Create Date: 2026-09-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260921_0007"
down_revision: str | None = "20260921_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "goal_contributions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_goal_contributions_amount_positive",
        ),
        sa.CheckConstraint(
            "source IN ("
            "'dashboard', 'whatsapp_text', 'whatsapp_audio', "
            "'whatsapp_image'"
            ")",
            name="ck_goal_contributions_source",
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_goal_contributions_user_id",
        "goal_contributions",
        ["user_id"],
    )
    op.create_index(
        "ix_goal_contributions_goal_id",
        "goal_contributions",
        ["goal_id"],
    )
    op.create_index(
        "ix_goal_contributions_created_at",
        "goal_contributions",
        ["created_at"],
    )

    op.create_table(
        "goal_contexts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_goal_contexts_user_id",
        "goal_contexts",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        "ix_goal_contexts_goal_id",
        "goal_contexts",
        ["goal_id"],
    )
    op.create_index(
        "ix_goal_contexts_expires_at",
        "goal_contexts",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_goal_contexts_expires_at", table_name="goal_contexts")
    op.drop_index("ix_goal_contexts_goal_id", table_name="goal_contexts")
    op.drop_index("ix_goal_contexts_user_id", table_name="goal_contexts")
    op.drop_table("goal_contexts")

    op.drop_index(
        "ix_goal_contributions_created_at",
        table_name="goal_contributions",
    )
    op.drop_index(
        "ix_goal_contributions_goal_id",
        table_name="goal_contributions",
    )
    op.drop_index(
        "ix_goal_contributions_user_id",
        table_name="goal_contributions",
    )
    op.drop_table("goal_contributions")
