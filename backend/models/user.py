from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    whatsapp_phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
        unique=True,
        index=True,
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    whatsapp_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    active: Mapped[bool] = mapped_column(
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

    categories: Mapped[list["Category"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    transactions: Mapped[list["FinancialTransaction"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    transaction_attachments: Mapped[list["TransactionAttachment"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    goals: Mapped[list["Goal"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    goal_contributions: Mapped[list["GoalContribution"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    financial_profile: Mapped["FinancialProfile | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


from backend.models.category import Category  # noqa: E402
from backend.models.financial_transaction import FinancialTransaction  # noqa: E402
from backend.models.financial_profile import FinancialProfile  # noqa: E402
from backend.models.goal import Goal  # noqa: E402
from backend.models.goal_contribution import GoalContribution  # noqa: E402
from backend.models.transaction_attachment import TransactionAttachment  # noqa: E402
