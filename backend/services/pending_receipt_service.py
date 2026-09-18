from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.pending_receipt import PendingReceipt
from backend.schemas.receipt_extraction import ReceiptExtraction


PENDING_RECEIPT_TTL = timedelta(minutes=10)
SENSITIVE_EXTRACTION_FIELDS = {"pix_key", "end_to_end_id"}


def create_pending_receipt(
    db: Session,
    *,
    user_id: int,
    whatsapp_message_id: str,
    extraction: ReceiptExtraction,
    current_time: datetime,
) -> PendingReceipt:
    existing = get_pending_receipt_by_message_id(db, whatsapp_message_id)
    if existing is not None:
        if existing.user_id != user_id:
            raise PermissionError("Comprovante pendente pertence a outro usuário")
        return existing

    db.execute(
        delete(PendingReceipt).where(PendingReceipt.user_id == user_id)
    )
    extracted_data = extraction.model_dump(
        mode="json",
        exclude=SENSITIVE_EXTRACTION_FIELDS,
    )
    pending = PendingReceipt(
        user_id=user_id,
        whatsapp_message_id=whatsapp_message_id,
        extracted_data=extracted_data,
        expires_at=current_time + PENDING_RECEIPT_TTL,
    )
    db.add(pending)

    try:
        db.commit()
        db.refresh(pending)
        return pending
    except IntegrityError:
        db.rollback()
        existing = get_pending_receipt_by_message_id(db, whatsapp_message_id)
        if existing is not None and existing.user_id == user_id:
            return existing
        raise


def get_pending_receipt_by_message_id(
    db: Session,
    whatsapp_message_id: str,
) -> PendingReceipt | None:
    return db.scalar(
        select(PendingReceipt).where(
            PendingReceipt.whatsapp_message_id == whatsapp_message_id
        )
    )


def get_latest_pending_receipt_for_user(
    db: Session,
    *,
    user_id: int,
) -> PendingReceipt | None:
    return db.scalar(
        select(PendingReceipt)
        .where(PendingReceipt.user_id == user_id)
        .order_by(PendingReceipt.created_at.desc(), PendingReceipt.id.desc())
        .limit(1)
    )


def update_pending_receipt_amount(
    db: Session,
    *,
    pending: PendingReceipt,
    user_id: int,
    amount: str,
) -> PendingReceipt:
    if pending.user_id != user_id:
        raise PermissionError("Comprovante pendente pertence a outro usuário")

    extracted_data = dict(pending.extracted_data)
    extracted_data["amount"] = amount
    pending.extracted_data = extracted_data

    try:
        db.commit()
        db.refresh(pending)
        return pending
    except SQLAlchemyError:
        db.rollback()
        raise


def delete_pending_receipt(
    db: Session,
    *,
    pending: PendingReceipt,
    user_id: int,
) -> None:
    if pending.user_id != user_id:
        raise PermissionError("Comprovante pendente pertence a outro usuário")

    try:
        db.delete(pending)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def pending_receipt_is_expired(
    pending: PendingReceipt,
    *,
    current_time: datetime,
) -> bool:
    expires_at = pending.expires_at
    if expires_at.tzinfo is None and current_time.tzinfo is not None:
        current_time = current_time.replace(tzinfo=None)
    elif expires_at.tzinfo is not None and current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=expires_at.tzinfo)
    return expires_at <= current_time
