from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user
from backend.database.connection import get_db
from backend.models.user import User
from backend.schemas.settings import SettingsResponse, SettingsUpdateRequest


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
    current_user.critical_spending_alerts_enabled = (
        payload.critical_spending_alerts_enabled
    )
    db.commit()
    db.refresh(current_user)
    return _response(current_user)


def _response(user: User) -> SettingsResponse:
    return SettingsResponse(
        user_id=user.id,
        critical_spending_alerts_enabled=(
            user.critical_spending_alerts_enabled
        ),
        updated_at=user.updated_at,
    )
