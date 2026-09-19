from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.pending_audio_confirmation import PendingAudioConfirmation


PENDING_AUDIO_TTL = timedelta(minutes=10)


def create_pending_audio_confirmation(
    db: Session,
    *,
    user_id: int,
    original_whatsapp_message_id: str,
    transcription: str,
    current_time: datetime,
) -> PendingAudioConfirmation:
    normalized_transcription = transcription.strip()
    if not normalized_transcription:
        raise ValueError("Transcrição vazia")

    existing = get_pending_audio_by_message_id(
        db,
        original_whatsapp_message_id,
    )
    if existing is not None:
        if existing.user_id != user_id:
            raise PermissionError("Confirmação de áudio pertence a outro usuário")
        return existing

    db.execute(
        delete(PendingAudioConfirmation).where(
            PendingAudioConfirmation.user_id == user_id
        )
    )
    pending = PendingAudioConfirmation(
        user_id=user_id,
        original_whatsapp_message_id=original_whatsapp_message_id,
        transcription=normalized_transcription[:4000],
        expires_at=current_time + PENDING_AUDIO_TTL,
    )
    db.add(pending)

    try:
        db.commit()
        db.refresh(pending)
        return pending
    except IntegrityError:
        db.rollback()
        existing = get_pending_audio_by_message_id(
            db,
            original_whatsapp_message_id,
        )
        if existing is not None and existing.user_id == user_id:
            return existing
        raise


def get_pending_audio_by_message_id(
    db: Session,
    original_whatsapp_message_id: str,
) -> PendingAudioConfirmation | None:
    return db.scalar(
        select(PendingAudioConfirmation).where(
            PendingAudioConfirmation.original_whatsapp_message_id
            == original_whatsapp_message_id
        )
    )


def get_latest_pending_audio_for_user(
    db: Session,
    *,
    user_id: int,
) -> PendingAudioConfirmation | None:
    return db.scalar(
        select(PendingAudioConfirmation)
        .where(PendingAudioConfirmation.user_id == user_id)
        .order_by(
            PendingAudioConfirmation.created_at.desc(),
            PendingAudioConfirmation.id.desc(),
        )
        .limit(1)
    )


def delete_pending_audio_confirmation(
    db: Session,
    *,
    pending: PendingAudioConfirmation,
    user_id: int,
) -> None:
    if pending.user_id != user_id:
        raise PermissionError("Confirmação de áudio pertence a outro usuário")
    try:
        db.delete(pending)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def append_pending_audio_complement(
    db: Session,
    *,
    pending: PendingAudioConfirmation,
    user_id: int,
    complement: str,
) -> PendingAudioConfirmation:
    if pending.user_id != user_id:
        raise PermissionError("Confirmação de áudio pertence a outro usuário")

    normalized_complement = " ".join(complement.split())
    if not normalized_complement:
        return pending

    pending.transcription = (
        f"{pending.transcription}\nComplemento do usuário: {normalized_complement}"
    )[:4000]
    try:
        db.commit()
        db.refresh(pending)
        return pending
    except SQLAlchemyError:
        db.rollback()
        raise


def pending_audio_is_expired(
    pending: PendingAudioConfirmation,
    *,
    current_time: datetime,
) -> bool:
    expires_at = pending.expires_at
    if expires_at.tzinfo is None and current_time.tzinfo is not None:
        current_time = current_time.replace(tzinfo=None)
    elif expires_at.tzinfo is not None and current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=expires_at.tzinfo)
    return expires_at <= current_time
