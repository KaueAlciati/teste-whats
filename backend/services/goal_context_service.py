from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.goal import Goal
from backend.models.goal_context import GoalContext


GOAL_CONTEXT_TTL = timedelta(minutes=30)


@dataclass(frozen=True)
class PendingGoalSelection:
    goal_ids: tuple[int, ...]
    expires_at: datetime


_pending_goal_selections: dict[tuple[object, int], PendingGoalSelection] = {}
_pending_goal_selections_lock = RLock()


def begin_goal_selection(
    db: Session,
    *,
    user_id: int,
    goal_ids: list[int],
    current_time: datetime,
) -> None:
    key = (db.get_bind(), user_id)
    with _pending_goal_selections_lock:
        if not goal_ids:
            _pending_goal_selections.pop(key, None)
            return
        _pending_goal_selections[key] = PendingGoalSelection(
            goal_ids=tuple(goal_ids),
            expires_at=current_time + GOAL_CONTEXT_TTL,
        )


def get_pending_goal_selection(
    db: Session,
    *,
    user_id: int,
    current_time: datetime,
) -> tuple[int, ...] | None:
    key = (db.get_bind(), user_id)
    with _pending_goal_selections_lock:
        pending = _pending_goal_selections.get(key)
        if pending is None:
            return None
        if _is_expired(pending.expires_at, current_time):
            _pending_goal_selections.pop(key, None)
            return None
        return pending.goal_ids


def clear_pending_goal_selection(db: Session, *, user_id: int) -> None:
    with _pending_goal_selections_lock:
        _pending_goal_selections.pop((db.get_bind(), user_id), None)


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
