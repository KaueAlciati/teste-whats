from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.pending_receipt import PendingReceipt
from backend.schemas.receipt_extraction import ReceiptExtraction
from backend.services.attachment_service import (
    StoredAttachment,
    delete_stored_file,
)


PENDING_RECEIPT_TTL = timedelta(minutes=10)
SENSITIVE_EXTRACTION_FIELDS = {"pix_key", "end_to_end_id"}
ATTACHMENT_DATA_KEY = "_attachment"
TRANSACTION_SOURCE_KEY = "_transaction_source"


def create_pending_receipt(
    db: Session,
    *,
    user_id: int,
    whatsapp_message_id: str,
    extraction: ReceiptExtraction,
    current_time: datetime,
    attachment: StoredAttachment | None = None,
    transaction_source: str = "whatsapp_image",
) -> PendingReceipt:
    existing = get_pending_receipt_by_message_id(db, whatsapp_message_id)
    if existing is not None:
        if existing.user_id != user_id:
            raise PermissionError("Comprovante pendente pertence a outro usuário")
        if attachment is not None:
            existing_attachment = get_pending_receipt_attachment(existing)
            if (
                existing_attachment is None
                or existing_attachment.storage_key != attachment.storage_key
            ):
                delete_stored_file(attachment.storage_key)
        return existing

    previous_pending = list(
        db.scalars(
            select(PendingReceipt).where(PendingReceipt.user_id == user_id)
        )
    )
    db.execute(delete(PendingReceipt).where(PendingReceipt.user_id == user_id))
    extracted_data = extraction.model_dump(
        mode="json",
        exclude=SENSITIVE_EXTRACTION_FIELDS,
    )
    if attachment is not None:
        extracted_data[ATTACHMENT_DATA_KEY] = {
            "storage_key": attachment.storage_key,
            "original_filename": attachment.original_filename,
            "mime_type": attachment.mime_type,
            "size_bytes": attachment.size_bytes,
            "sha256": attachment.sha256,
        }
    extracted_data[TRANSACTION_SOURCE_KEY] = transaction_source
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
        for previous in previous_pending:
            previous_attachment = get_pending_receipt_attachment(previous)
            if previous_attachment is not None:
                delete_stored_file(previous_attachment.storage_key)
        return pending
    except IntegrityError:
        db.rollback()
        existing = get_pending_receipt_by_message_id(db, whatsapp_message_id)
        if existing is not None and existing.user_id == user_id:
            if attachment is not None:
                existing_attachment = get_pending_receipt_attachment(existing)
                if (
                    existing_attachment is None
                    or existing_attachment.storage_key != attachment.storage_key
                ):
                    delete_stored_file(attachment.storage_key)
            return existing
        if attachment is not None:
            delete_stored_file(attachment.storage_key)
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
    return update_pending_receipt_fields(
        db,
        pending=pending,
        user_id=user_id,
        changes={"amount": amount},
    )


def update_pending_receipt_fields(
    db: Session,
    *,
    pending: PendingReceipt,
    user_id: int,
    changes: dict[str, object],
) -> PendingReceipt:
    if pending.user_id != user_id:
        raise PermissionError("Comprovante pendente pertence a outro usuário")

    extracted_data = dict(pending.extracted_data)
    extracted_data.update(changes)
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

    attachment = get_pending_receipt_attachment(pending)
    try:
        db.delete(pending)
        db.commit()
        if attachment is not None:
            delete_stored_file(attachment.storage_key)
    except SQLAlchemyError:
        db.rollback()
        raise


def receipt_extraction_from_pending(pending: PendingReceipt) -> ReceiptExtraction:
    extraction_data = {
        key: value
        for key, value in pending.extracted_data.items()
        if key not in {ATTACHMENT_DATA_KEY, TRANSACTION_SOURCE_KEY}
    }
    return ReceiptExtraction.model_validate(extraction_data)


def get_pending_receipt_attachment(
    pending: PendingReceipt,
) -> StoredAttachment | None:
    raw = pending.extracted_data.get(ATTACHMENT_DATA_KEY)
    if not isinstance(raw, dict):
        return None
    try:
        return StoredAttachment(
            storage_key=str(raw["storage_key"]),
            original_filename=str(raw["original_filename"]),
            mime_type=str(raw["mime_type"]),
            size_bytes=int(raw["size_bytes"]),
            sha256=str(raw["sha256"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def get_pending_receipt_source(pending: PendingReceipt) -> str:
    source = pending.extracted_data.get(TRANSACTION_SOURCE_KEY)
    if source in {"whatsapp_image", "whatsapp_document"}:
        return str(source)
    return "whatsapp_image"


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
