from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class TransactionAttachment(Base):
    __tablename__ = "transaction_attachments"
    __table_args__ = (
        CheckConstraint(
            "mime_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name="ck_transaction_attachments_mime_type",
        ),
        CheckConstraint(
            "size_bytes > 0",
            name="ck_transaction_attachments_size_bytes",
        ),
        UniqueConstraint(
            "transaction_id",
            "storage_key",
            name="uq_transaction_attachments_transaction_storage",
        ),
        Index(
            "ix_transaction_attachments_user_transaction",
            "user_id",
            "transaction_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("financial_transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="transaction_attachments")
    transaction: Mapped["FinancialTransaction"] = relationship(
        back_populates="attachments"
    )


from backend.models.financial_transaction import FinancialTransaction  # noqa: E402
from backend.models.user import User  # noqa: E402
