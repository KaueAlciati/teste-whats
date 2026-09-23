"""Adiciona preferência e notificações de gastos críticos.

Revision ID: 20260923_0013
Revises: 20260922_0012
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260923_0013"
down_revision: str | None = "20260922_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "critical_spending_alerts_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rule_code", sa.String(length=50), nullable=False),
        sa.Column("period_key", sa.String(length=7), nullable=False),
        sa.Column("action_url", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('financeiro', 'sistema', 'ia', 'seguranca', "
            "'atualizacoes', 'lembretes')",
            name="ck_notifications_category",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="ck_notifications_priority",
        ),
        sa.CheckConstraint(
            "status IN ('unread', 'read')",
            name="ck_notifications_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "rule_code",
            "period_key",
            name="uq_notifications_user_rule_period",
        ),
    )
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_user_status",
        "notifications",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_status", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_column("users", "critical_spending_alerts_enabled")
