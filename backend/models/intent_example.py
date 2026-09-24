from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class IntentExample(Base):
    __tablename__ = "intent_examples"
    __table_args__ = (
        CheckConstraint(
            "source IN ('seed', 'manual', 'reviewed')",
            name="ck_intent_examples_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    phrase: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
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
