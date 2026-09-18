"""Cria estrutura inicial do banco financeiro.

Revision ID: 20260918_0001
Revises:
Create Date: 2026-09-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260918_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_CATEGORIES = {
    "expense": (
        "Alimentação",
        "Transporte",
        "Moradia",
        "Saúde",
        "Educação",
        "Lazer",
        "Compras",
        "Assinaturas",
        "Contas",
        "Impostos",
        "Outros",
    ),
    "income": (
        "Salário",
        "Freelance",
        "Venda",
        "Investimentos",
        "Reembolso",
        "Outros",
    ),
}


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("whatsapp_phone", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_users_whatsapp_phone",
        "users",
        ["whatsapp_phone"],
        unique=True,
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('expense', 'income')",
            name="ck_categories_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_categories_user_id",
        "categories",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "uq_categories_system_name_type",
        "categories",
        ["name", "type"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
        sqlite_where=sa.text("user_id IS NULL"),
    )
    op.create_index(
        "uq_categories_user_name_type",
        "categories",
        ["user_id", "name", "type"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
        sqlite_where=sa.text("user_id IS NOT NULL"),
    )

    op.create_table(
        "financial_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("whatsapp_message_id", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "amount > 0",
            name="ck_financial_transactions_amount",
        ),
        sa.CheckConstraint(
            "source IN ("
            "'whatsapp_text', 'whatsapp_audio', 'whatsapp_image', "
            "'whatsapp_document', 'web'"
            ")",
            name="ck_financial_transactions_source",
        ),
        sa.CheckConstraint(
            "type IN ('expense', 'income')",
            name="ck_financial_transactions_type",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_financial_transactions_category_id",
        "financial_transactions",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_transactions_transaction_date",
        "financial_transactions",
        ["transaction_date"],
        unique=False,
    )
    op.create_index(
        "ix_financial_transactions_type",
        "financial_transactions",
        ["type"],
        unique=False,
    )
    op.create_index(
        "ix_financial_transactions_user_id",
        "financial_transactions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_transactions_whatsapp_message_id",
        "financial_transactions",
        ["whatsapp_message_id"],
        unique=True,
    )

    categories = sa.table(
        "categories",
        sa.column("name", sa.String()),
        sa.column("type", sa.String()),
        sa.column("user_id", sa.Integer()),
        sa.column("is_default", sa.Boolean()),
    )
    connection = op.get_bind()

    for category_type, category_names in DEFAULT_CATEGORIES.items():
        for category_name in category_names:
            category_exists = connection.execute(
                sa.select(sa.literal(1))
                .select_from(categories)
                .where(
                    categories.c.name == category_name,
                    categories.c.type == category_type,
                    categories.c.user_id.is_(None),
                )
                .limit(1)
            ).scalar()
            if category_exists is None:
                connection.execute(
                    categories.insert().values(
                        name=category_name,
                        type=category_type,
                        user_id=None,
                        is_default=True,
                    )
                )


def downgrade() -> None:
    op.drop_table("financial_transactions")
    op.drop_table("categories")
    op.drop_table("users")
