from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.goal import Goal
from backend.models.goal_context import GoalContext


GOAL_CONTEXT_TTL = timedelta(minutes=30)


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
