from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class IntentClarification(Base):
    __tablename__ = "intent_clarifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    unrecognized_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("unrecognized_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_message: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    candidates: Mapped[list] = mapped_column(JSON, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
