from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.goal import Goal
from backend.models.goal_contribution import GoalContribution
from backend.services.insights_invalidation_service import mark_insights_stale


GOAL_CONTRIBUTION_SOURCES = {
    "dashboard",
    "whatsapp_text",
    "whatsapp_audio",
    "whatsapp_image",
}


@dataclass(frozen=True)
class GoalContributionResult:
    contribution: GoalContribution
    goal: Goal
    percent: Decimal
    missing: Decimal


def add_goal_contribution(
    db: Session,
    *,
    goal_id: int,
    user_id: int,
    amount: Decimal | float | str,
    source: str,
) -> GoalContributionResult:
    if source not in GOAL_CONTRIBUTION_SOURCES:
        raise ValueError("Origem de aporte inválida")

    normalized_amount = _positive_money(amount)
    goal = db.scalar(
        select(Goal)
        .where(Goal.id == goal_id, Goal.user_id == user_id)
        .with_for_update()
    )
    if goal is None:
        raise LookupError("Meta não encontrada")
    if goal.status == "completed":
        raise ValueError("Essa meta já foi concluída")

    contribution = GoalContribution(
        user_id=user_id,
        goal_id=goal.id,
        amount=normalized_amount,
        source=source,
    )
    goal.current_amount += normalized_amount
    if goal.current_amount >= goal.target_amount:
        goal.status = "completed"
    db.add(contribution)

    try:
        mark_insights_stale(db, user_id=user_id)
        db.commit()
        db.refresh(contribution)
        db.refresh(goal)
    except SQLAlchemyError:
        db.rollback()
        raise

    percent = min(
        Decimal("100.00"),
        ((goal.current_amount / goal.target_amount) * Decimal("100")).quantize(
            Decimal("0.01")
        ),
    )
    missing = max(Decimal("0.00"), goal.target_amount - goal.current_amount)
    return GoalContributionResult(
        contribution=contribution,
        goal=goal,
        percent=percent,
        missing=missing,
    )


def list_goal_contributions(
    db: Session,
    *,
    goal_id: int,
    user_id: int,
) -> list[GoalContribution]:
    return list(
        db.scalars(
            select(GoalContribution)
            .where(
                GoalContribution.goal_id == goal_id,
                GoalContribution.user_id == user_id,
            )
            .order_by(
                GoalContribution.created_at.desc(),
                GoalContribution.id.desc(),
            )
        )
    )


def _positive_money(value: Decimal | float | str) -> Decimal:
    try:
        normalized = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("Valor do aporte inválido") from exc
    if not normalized.is_finite() or normalized <= 0:
        raise ValueError("O aporte deve ser maior que zero")
    return normalized
