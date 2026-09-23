from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "category IN ('financeiro', 'sistema', 'ia', 'seguranca', "
            "'atualizacoes', 'lembretes')",
            name="ck_notifications_category",
        ),
        CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'urgent')",
            name="ck_notifications_priority",
        ),
        CheckConstraint(
            "status IN ('unread', 'read')",
            name="ck_notifications_status",
        ),
        UniqueConstraint(
            "user_id",
            "rule_code",
            "period_key",
            name="uq_notifications_user_rule_period",
        ),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(50), nullable=False)
    period_key: Mapped[str] = mapped_column(String(7), nullable=False)
    action_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="notifications")


from backend.models.user import User  # noqa: E402
