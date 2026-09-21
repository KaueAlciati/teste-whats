"""Adiciona perfil financeiro para onboarding e cache de insights.

Revision ID: 20260921_0008
Revises: 20260921_0007
Create Date: 2026-09-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260921_0008"
down_revision: str | None = "20260921_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("main_goal", sa.String(length=40), nullable=False),
        sa.Column("investment_horizon", sa.String(length=40), nullable=False),
        sa.Column("risk_profile", sa.String(length=20), nullable=False),
        sa.Column("liquidity_need", sa.String(length=20), nullable=False),
        sa.Column("has_debts", sa.Boolean(), nullable=False),
        sa.Column("income_type", sa.String(length=20), nullable=False),
        sa.Column("main_priority", sa.String(length=40), nullable=False),
        sa.Column(
            "onboarding_completed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("analysis_cache", sa.JSON(), nullable=True),
        sa.Column("analysis_generated_at", sa.DateTime(timezone=True), nullable=True),
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
            "main_goal IN ("
            "'emergency_reserve', 'pay_debts', 'purchase_goal', "
            "'organize_finances', 'invest_future', 'grow_wealth'"
            ")",
            name="ck_financial_profiles_main_goal",
        ),
        sa.CheckConstraint(
            "investment_horizon IN ("
            "'up_to_6_months', 'up_to_1_year', 'one_to_three_years', "
            "'three_to_five_years', 'more_than_five_years'"
            ")",
            name="ck_financial_profiles_investment_horizon",
        ),
        sa.CheckConstraint(
            "risk_profile IN ('conservative', 'moderate', 'aggressive')",
            name="ck_financial_profiles_risk_profile",
        ),
        sa.CheckConstraint(
            "liquidity_need IN ('high', 'medium', 'low')",
            name="ck_financial_profiles_liquidity_need",
        ),
        sa.CheckConstraint(
            "income_type IN ('fixed', 'variable', 'mixed')",
            name="ck_financial_profiles_income_type",
        ),
        sa.CheckConstraint(
            "main_priority IN ("
            "'reduce_expenses', 'organize_budget', 'achieve_goals', "
            "'start_investing', 'increase_savings'"
            ")",
            name="ck_financial_profiles_main_priority",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_financial_profiles_user_id",
        "financial_profiles",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_financial_profiles_user_id", table_name="financial_profiles")
    op.drop_table("financial_profiles")
