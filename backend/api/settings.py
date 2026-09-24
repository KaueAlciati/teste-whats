from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user
from backend.database.connection import get_db
from backend.models.user import User
from backend.schemas.settings import SettingsResponse, SettingsUpdateRequest
from backend.services.insights_invalidation_service import mark_insights_stale


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(
    current_user: User = Depends(get_current_user),
) -> SettingsResponse:
    return _response(current_user)


@router.put("", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SettingsResponse:
    if payload.critical_spending_alerts_enabled is not None:
        current_user.critical_spending_alerts_enabled = (
            payload.critical_spending_alerts_enabled
        )
    if payload.ai_enabled is not None:
        was_enabled = current_user.automatic_insights_enabled
        current_user.automatic_insights_enabled = payload.ai_enabled
        if payload.ai_enabled and not was_enabled:
            mark_insights_stale(db, user_id=current_user.id)
    db.commit()
    db.refresh(current_user)
    return _response(current_user)


def _response(user: User) -> SettingsResponse:
    return SettingsResponse(
        user_id=user.id,
        critical_spending_alerts_enabled=(
            user.critical_spending_alerts_enabled
        ),
        ai_enabled=user.automatic_insights_enabled,
        updated_at=user.updated_at,
    )
