from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import case, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.goal import Goal


def list_goals(db: Session, *, user_id: int) -> list[Goal]:
    statement = (
        select(Goal)
        .where(Goal.user_id == user_id)
        .order_by(
            case((Goal.status == "active", 0), else_=1),
            Goal.target_date.asc().nulls_last(),
            Goal.id.desc(),
        )
    )
    return list(db.scalars(statement))


def get_goal(db: Session, *, goal_id: int, user_id: int) -> Goal | None:
    return db.scalar(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    )


def create_goal(
    db: Session,
    *,
    user_id: int,
    name: str,
    target_amount: Decimal,
    target_date: date | None,
) -> Goal:
    goal = Goal(
        user_id=user_id,
        name=name,
        target_amount=_money(target_amount),
        current_amount=Decimal("0.00"),
        target_date=target_date,
        status="active",
    )
    db.add(goal)
    try:
        db.commit()
        db.refresh(goal)
        return goal
    except SQLAlchemyError:
        db.rollback()
        raise


def update_goal(
    db: Session,
    *,
    goal: Goal,
    user_id: int,
    changes: dict,
) -> Goal:
    if goal.user_id != user_id:
        raise PermissionError("Meta pertence a outro usuário")

    if "name" in changes:
        goal.name = changes["name"]
    if "target_amount" in changes:
        goal.target_amount = _money(changes["target_amount"])
    if "target_date" in changes:
        goal.target_date = changes["target_date"]
    requested_status = changes.get("status")
    if requested_status == "completed":
        goal.status = "completed"
    elif requested_status == "active":
        goal.status = "active"
    elif "target_amount" in changes:
        goal.status = (
            "completed"
            if goal.current_amount >= goal.target_amount
            else "active"
        )

    try:
        db.commit()
        db.refresh(goal)
        return goal
    except SQLAlchemyError:
        db.rollback()
        raise


def delete_goal(db: Session, *, goal: Goal, user_id: int) -> None:
    if goal.user_id != user_id:
        raise PermissionError("Meta pertence a outro usuário")

    try:
        db.delete(goal)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def _money(value: Decimal) -> Decimal:
    try:
        normalized = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("Valor monetário inválido") from exc
    if normalized < 0:
        raise ValueError("Valor monetário inválido")
    return normalized
