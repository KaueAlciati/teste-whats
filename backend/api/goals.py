from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user
from backend.database.connection import get_db
from backend.models.goal import Goal
from backend.models.user import User
from backend.schemas.goal import GoalCreate, GoalResponse, GoalUpdate
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
    updated = update_goal(
        db,
        goal=goal,
        user_id=current_user.id,
        changes=payload.model_dump(exclude_unset=True),
    )
    return _goal_response(updated)


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
    target = goal.target_amount
    current = goal.current_amount
    percent = min(Decimal("100"), (current / target) * Decimal("100"))
    return GoalResponse(
        id=goal.id,
        goal_name=goal.name,
        target=float(target),
        current=float(current),
        missing=float(max(Decimal("0.00"), target - current)),
        percent=float(percent.quantize(Decimal("0.01"))),
        deadline=goal.target_date,
        completed=goal.status == "completed",
    )
