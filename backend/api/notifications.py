from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user
from backend.database.connection import get_db
from backend.models.user import User
from backend.schemas.notification import (
    NotificationCategory,
    NotificationListResponse,
    NotificationPriority,
    NotificationResponse,
    NotificationStatus,
)
from backend.services.notification_service import (
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    notification_response,
)


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def get_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=120),
    category: NotificationCategory | None = None,
    priority: NotificationPriority | None = None,
    notification_status: NotificationStatus | None = Query(None, alias="status"),
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationListResponse:
    items, total = list_notifications(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        query=q,
        category=category,
        priority=priority,
        notification_status=notification_status,
        date_from=date_from,
        date_to=date_to,
    )
    return NotificationListResponse(
        items=[
            NotificationResponse.model_validate(notification_response(item))
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/read-all")
def read_all_notifications(
    q: str | None = Query(None, max_length=120),
    category: NotificationCategory | None = None,
    priority: NotificationPriority | None = None,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    mark_all_notifications_read(
        db,
        user_id=current_user.id,
        query=q,
        category=category,
        priority=priority,
        date_from=date_from,
        date_to=date_to,
    )
    return {"ok": True}


@router.post("/{notification_id}/read")
def read_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if not mark_notification_read(
        db,
        user_id=current_user.id,
        notification_id=notification_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificação não encontrada",
        )
    return {"ok": True}
