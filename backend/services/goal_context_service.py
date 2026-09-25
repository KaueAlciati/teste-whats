from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.goal import Goal
from backend.models.goal_context import GoalContext
from backend.models.intent_clarification import IntentClarification


GOAL_CONTEXT_TTL = timedelta(minutes=30)


@dataclass(frozen=True)
class PendingGoalSelection:
    goal_ids: tuple[int, ...]
    action: str
    expires_at: datetime


GOAL_SELECTION_INTENT = "goal_selection"


def begin_goal_selection(
    db: Session,
    *,
    user_id: int,
    goal_ids: list[int],
    current_time: datetime,
    action: str = "select",
    original_message: str = "",
    source: str = "whatsapp_text",
) -> None:
    existing = db.scalar(
        select(IntentClarification).where(IntentClarification.user_id == user_id)
    )
    if existing is not None:
        db.delete(existing)
        db.flush()
    if not goal_ids:
        db.commit()
        return
    db.add(
        IntentClarification(
            user_id=user_id,
            unrecognized_message_id=None,
            original_message=original_message[:4000],
            suggested_intent=GOAL_SELECTION_INTENT,
            candidates=[str(goal_id) for goal_id in goal_ids],
            parameters={"goal_ids": goal_ids, "action": action},
            source=(
                "whatsapp_audio" if source == "whatsapp_audio" else "whatsapp_text"
            ),
            expires_at=current_time + GOAL_CONTEXT_TTL,
        )
    )
    db.commit()


def get_pending_goal_selection(
    db: Session,
    *,
    user_id: int,
    current_time: datetime,
) -> PendingGoalSelection | None:
    clarification = db.scalar(
        select(IntentClarification).where(
            IntentClarification.user_id == user_id,
            IntentClarification.suggested_intent == GOAL_SELECTION_INTENT,
        )
    )
    if clarification is None:
        return None
    if _is_expired(clarification.expires_at, current_time):
        db.delete(clarification)
        db.commit()
        return None
    parameters = clarification.parameters or {}
    raw_goal_ids = parameters.get("goal_ids", clarification.candidates or [])
    try:
        goal_ids = tuple(int(goal_id) for goal_id in raw_goal_ids)
    except (TypeError, ValueError):
        clear_pending_goal_selection(db, user_id=user_id)
        return None
    return PendingGoalSelection(
        goal_ids=goal_ids,
        action=str(parameters.get("action") or "select"),
        expires_at=clarification.expires_at,
    )


def clear_pending_goal_selection(db: Session, *, user_id: int) -> None:
    clarification = db.scalar(
        select(IntentClarification).where(
            IntentClarification.user_id == user_id,
            IntentClarification.suggested_intent == GOAL_SELECTION_INTENT,
        )
    )
    if clarification is not None:
        db.delete(clarification)
        db.commit()


def select_goal_context(
    db: Session,
    *,
    user_id: int,
    goal: Goal,
    current_time: datetime,
) -> GoalContext:
    if goal.user_id != user_id:
        raise PermissionError("Meta pertence a outro usuário")

    context = db.scalar(
        select(GoalContext).where(GoalContext.user_id == user_id)
    )
    if context is None:
        context = GoalContext(
            user_id=user_id,
            goal_id=goal.id,
            expires_at=current_time + GOAL_CONTEXT_TTL,
        )
        db.add(context)
    else:
        context.goal_id = goal.id
        context.expires_at = current_time + GOAL_CONTEXT_TTL

    try:
        db.commit()
        db.refresh(context)
        clear_pending_goal_selection(db, user_id=user_id)
        return context
    except IntegrityError:
        db.rollback()
        context = db.scalar(
            select(GoalContext).where(GoalContext.user_id == user_id)
        )
        if context is None:
            raise
        context.goal_id = goal.id
        context.expires_at = current_time + GOAL_CONTEXT_TTL
        db.commit()
        db.refresh(context)
        clear_pending_goal_selection(db, user_id=user_id)
        return context


def get_selected_goal(
    db: Session,
    *,
    user_id: int,
    current_time: datetime,
) -> Goal | None:
    context = db.scalar(
        select(GoalContext).where(GoalContext.user_id == user_id)
    )
    if context is None:
        return None
    if _is_expired(context.expires_at, current_time):
        db.delete(context)
        db.commit()
        return None

    goal = db.scalar(
        select(Goal).where(
            Goal.id == context.goal_id,
            Goal.user_id == user_id,
        )
    )
    if goal is None:
        db.delete(context)
        db.commit()
        return None

    context.expires_at = current_time + GOAL_CONTEXT_TTL
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return goal


def _is_expired(expires_at: datetime, current_time: datetime) -> bool:
    if expires_at.tzinfo is None and current_time.tzinfo is not None:
        current_time = current_time.replace(tzinfo=None)
    elif expires_at.tzinfo is not None and current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=expires_at.tzinfo)
    return expires_at <= current_time
