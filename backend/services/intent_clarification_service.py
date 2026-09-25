from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.intent_clarification import IntentClarification
from backend.models.unrecognized_message import UnrecognizedMessage
from backend.schemas.natural_intent import (
    NaturalIntentDecision,
    NaturalIntentParameters,
)
from backend.services.natural_period_service import normalize_language


CLARIFICATION_TTL = timedelta(minutes=15)


def record_unrecognized_message(
    db: Session,
    *,
    user_id: int,
    message: str,
    source: str,
    detected_intent: str | None = None,
    confidence: float | None = None,
    commit: bool = True,
) -> UnrecognizedMessage:
    record = UnrecognizedMessage(
        user_id=user_id,
        message=message.strip()[:4000],
        detected_intent=detected_intent,
        confidence=confidence,
        source=_source(source),
        reviewed=False,
    )
    db.add(record)
    if commit:
        db.commit()
        db.refresh(record)
    else:
        db.flush()
    return record


def begin_intent_clarification(
    db: Session,
    *,
    user_id: int,
    message: str,
    source: str,
    decision: NaturalIntentDecision,
    current_time: datetime,
) -> IntentClarification:
    existing = db.scalar(
        select(IntentClarification).where(IntentClarification.user_id == user_id)
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    unrecognized = record_unrecognized_message(
        db,
        user_id=user_id,
        message=message,
        source=source,
        detected_intent=(decision.intent if decision.intent != "unknown" else None),
        confidence=decision.confidence,
        commit=False,
    )
    clarification = IntentClarification(
        user_id=user_id,
        unrecognized_message_id=unrecognized.id,
        original_message=message.strip()[:4000],
        suggested_intent=(decision.intent if decision.intent != "unknown" else None),
        candidates=list(decision.candidates),
        parameters=decision.parameters.model_dump(mode="json"),
        source=_source(source),
        expires_at=current_time + CLARIFICATION_TTL,
    )
    db.add(clarification)
    db.commit()
    db.refresh(clarification)
    return clarification


def resolve_intent_clarification(
    db: Session,
    *,
    user_id: int,
    reply: str,
    current_time: datetime,
) -> NaturalIntentDecision | None:
    clarification = db.scalar(
        select(IntentClarification).where(IntentClarification.user_id == user_id)
    )
    if clarification is None:
        return None
    if clarification.suggested_intent == "goal_selection":
        return None
    if _expired(clarification.expires_at, current_time):
        db.delete(clarification)
        db.commit()
        return None

    normalized = normalize_language(reply)
    selected: str | None = None
    candidates = set(clarification.candidates or [])
    if "consultar_maior_gasto" in candidates and (
        normalized in {"individual", "despesa", "maior despesa", "gasto individual"}
        or "individual" in normalized
        or "maior despesa" in normalized
    ):
        selected = "consultar_maior_gasto"
    elif "consultar_categoria_maior_gasto" in candidates and (
        normalized in {"categoria", "por categoria", "categoria de gasto"}
        or "categoria" in normalized
    ):
        selected = "consultar_categoria_maior_gasto"
    elif normalized in {"sim", "isso", "pode", "exato"} and clarification.suggested_intent:
        selected = clarification.suggested_intent

    if selected is None:
        return None

    if clarification.unrecognized_message_id is not None:
        original = db.get(
            UnrecognizedMessage,
            clarification.unrecognized_message_id,
        )
        if original is not None:
            original.resolved_intent = selected
    correction = record_unrecognized_message(
        db,
        user_id=user_id,
        message=reply,
        source=clarification.source,
        detected_intent=clarification.suggested_intent,
        confidence=None,
        commit=False,
    )
    correction.resolved_intent = selected
    parameters = NaturalIntentParameters.model_validate(
        clarification.parameters or {}
    )
    db.delete(clarification)
    db.commit()
    return NaturalIntentDecision(
        intent=selected,
        confidence=1.0,
        parameters=parameters,
        clarification_question=None,
        candidates=[],
    )


def clear_intent_clarification(db: Session, *, user_id: int) -> None:
    clarification = db.scalar(
        select(IntentClarification).where(IntentClarification.user_id == user_id)
    )
    if clarification is not None:
        db.delete(clarification)
        db.commit()


def _source(source: str) -> str:
    return "whatsapp_audio" if source == "whatsapp_audio" else "whatsapp_text"


def _expired(expires_at: datetime, current_time: datetime) -> bool:
    left = expires_at
    right = current_time
    if left.tzinfo is None and right.tzinfo is not None:
        left = left.replace(tzinfo=right.tzinfo)
    if right.tzinfo is None and left.tzinfo is not None:
        right = right.replace(tzinfo=left.tzinfo)
    return left <= right
