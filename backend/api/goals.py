from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user
from backend.database.connection import get_db
from backend.models.goal import Goal
from backend.models.user import User
from backend.schemas.goal import (
    GoalContributionCreate,
    GoalContributionResponse,
    GoalCreate,
    GoalResponse,
    GoalUpdate,
)
from backend.services.goal_contribution_service import (
    GoalContributionResult,
    add_goal_contribution,
    list_goal_contributions,
)
from backend.services.goal_service import (
    create_goal,
    delete_goal,
    get_goal,
    list_goals,
    update_goal,
)


router = APIRouter(prefix="/api/goals", tags=["goals"])


@router.get("", response_model=list[GoalResponse])
def get_goals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GoalResponse]:
    return [
        _goal_response(goal)
        for goal in list_goals(db, user_id=current_user.id)
    ]


@router.post(
    "",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_goal(
    payload: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoalResponse:
    goal = create_goal(
        db,
        user_id=current_user.id,
        name=payload.name,
        target_amount=payload.target_amount,
        target_date=payload.target_date,
    )
    return _goal_response(goal)


@router.put("/{goal_id}", response_model=GoalResponse)
def put_goal(
    goal_id: int,
    payload: GoalUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoalResponse:
    goal = _owned_goal(db, goal_id, current_user.id)
    changes = payload.model_dump(exclude_unset=True)
    contribution_amount = changes.pop("current_amount_delta", None)
    if contribution_amount is not None:
        try:
            result = add_goal_contribution(
                db,
                goal_id=goal.id,
                user_id=current_user.id,
                amount=contribution_amount,
                source="dashboard",
            )
            return _goal_response(result.goal)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from None
    if (
        changes.get("status") == "completed"
        and goal.current_amount < goal.target_amount
    ):
        result = add_goal_contribution(
            db,
            goal_id=goal.id,
            user_id=current_user.id,
            amount=goal.target_amount - goal.current_amount,
            source="dashboard",
        )
        return _goal_response(result.goal)
    updated = update_goal(
        db,
        goal=goal,
        user_id=current_user.id,
        changes=changes,
    )
    return _goal_response(updated)


@router.get(
    "/{goal_id}/contributions",
    response_model=list[GoalContributionResponse],
)
def get_contributions(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GoalContributionResponse]:
    goal = _owned_goal(db, goal_id, current_user.id)
    current, missing, percent = _goal_progress(goal)
    return [
        GoalContributionResponse(
            id=contribution.id,
            goal_id=contribution.goal_id,
            amount=float(contribution.amount),
            source=contribution.source,
            created_at=contribution.created_at,
            current_amount=float(current),
            missing=float(missing),
            percent=float(percent),
        )
        for contribution in list_goal_contributions(
            db,
            goal_id=goal.id,
            user_id=current_user.id,
        )
    ]


@router.post(
    "/{goal_id}/contributions",
    response_model=GoalContributionResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_contribution(
    goal_id: int,
    payload: GoalContributionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoalContributionResponse:
    goal = _owned_goal(db, goal_id, current_user.id)
    try:
        result = add_goal_contribution(
            db,
            goal_id=goal.id,
            user_id=current_user.id,
            amount=payload.amount,
            source="dashboard",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None
    return _contribution_response(result)


@router.delete("/{goal_id}")
def remove_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    goal = _owned_goal(db, goal_id, current_user.id)
    delete_goal(db, goal=goal, user_id=current_user.id)
    return {"status": "ok"}


def _owned_goal(db: Session, goal_id: int, user_id: int) -> Goal:
    goal = get_goal(db, goal_id=goal_id, user_id=user_id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meta não encontrada",
        )
    return goal


def _goal_response(goal: Goal) -> GoalResponse:
    current, missing, percent = _goal_progress(goal)
    return GoalResponse(
        id=goal.id,
        goal_name=goal.name,
        target=float(goal.target_amount),
        current=float(current),
        missing=float(missing),
        percent=float(percent),
        deadline=goal.target_date,
        completed=goal.status == "completed",
    )


def _contribution_response(
    result: GoalContributionResult,
) -> GoalContributionResponse:
    return GoalContributionResponse(
        id=result.contribution.id,
        goal_id=result.goal.id,
        amount=float(result.contribution.amount),
        source=result.contribution.source,
        created_at=result.contribution.created_at,
        current_amount=float(result.goal.current_amount),
        missing=float(result.missing),
        percent=float(result.percent),
    )


def _goal_progress(goal: Goal) -> tuple[Decimal, Decimal, Decimal]:
    current = goal.current_amount
    missing = max(Decimal("0.00"), goal.target_amount - current)
    percent = min(
        Decimal("100.00"),
        ((current / goal.target_amount) * Decimal("100")).quantize(
            Decimal("0.01")
        ),
    )
    return current, missing, percent
