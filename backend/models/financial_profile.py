from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class FinancialProfile(Base):
    __tablename__ = "financial_profiles"
    __table_args__ = (
        CheckConstraint(
            "main_goal IN ("
            "'emergency_reserve', 'pay_debts', 'purchase_goal', "
            "'organize_finances', 'invest_future', 'grow_wealth'"
            ")",
            name="ck_financial_profiles_main_goal",
        ),
        CheckConstraint(
            "investment_horizon IN ("
            "'up_to_6_months', 'up_to_1_year', 'one_to_three_years', "
            "'three_to_five_years', 'more_than_five_years'"
            ")",
            name="ck_financial_profiles_investment_horizon",
        ),
        CheckConstraint(
            "risk_profile IN ('conservative', 'moderate', 'aggressive')",
            name="ck_financial_profiles_risk_profile",
        ),
        CheckConstraint(
            "liquidity_need IN ('high', 'medium', 'low')",
            name="ck_financial_profiles_liquidity_need",
        ),
        CheckConstraint(
            "income_type IN ('fixed', 'variable', 'mixed')",
            name="ck_financial_profiles_income_type",
        ),
        CheckConstraint(
            "main_priority IN ("
            "'reduce_expenses', 'organize_budget', 'achieve_goals', "
            "'start_investing', 'increase_savings'"
            ")",
            name="ck_financial_profiles_main_priority",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    main_goal: Mapped[str] = mapped_column(String(40), nullable=False)
    investment_horizon: Mapped[str] = mapped_column(String(40), nullable=False)
    risk_profile: Mapped[str] = mapped_column(String(20), nullable=False)
    liquidity_need: Mapped[str] = mapped_column(String(20), nullable=False)
    has_debts: Mapped[bool] = mapped_column(Boolean, nullable=False)
    income_type: Mapped[str] = mapped_column(String(20), nullable=False)
    main_priority: Mapped[str] = mapped_column(String(40), nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    analysis_cache: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analysis_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    analysis_stale: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="financial_profile")


from backend.models.user import User  # noqa: E402
