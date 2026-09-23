from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from backend.models.notification import Notification


def list_notifications(
    db: Session,
    *,
    user_id: int,
    page: int,
    page_size: int,
    query: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    notification_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[list[Notification], int]:
    filters = _filters(
        user_id=user_id,
        query=query,
        category=category,
        priority=priority,
        notification_status=notification_status,
        date_from=date_from,
        date_to=date_to,
    )
    total = db.scalar(
        select(func.count(Notification.id)).where(*filters)
    ) or 0
    items = list(
        db.scalars(
            select(Notification)
            .where(*filters)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, int(total)


def mark_notification_read(
    db: Session,
    *,
    user_id: int,
    notification_id: int,
) -> bool:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    if notification is None:
        return False
    if notification.status != "read":
        notification.status = "read"
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
    return True


def mark_all_notifications_read(
    db: Session,
    *,
    user_id: int,
    query: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> None:
    filters = _filters(
        user_id=user_id,
        query=query,
        category=category,
        priority=priority,
        notification_status="unread",
        date_from=date_from,
        date_to=date_to,
    )
    db.execute(
        update(Notification)
        .where(*filters)
        .values(status="read", read_at=datetime.now(timezone.utc))
    )
    db.commit()


def notification_response(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "title": notification.title,
        "description": notification.description,
        "category": notification.category,
        "priority": notification.priority,
        "status": notification.status,
        "created_at": notification.created_at,
        "read_at": notification.read_at,
        "action_url": notification.action_url,
        "metadata": notification.data,
    }


def _filters(
    *,
    user_id: int,
    query: str | None,
    category: str | None,
    priority: str | None,
    notification_status: str | None,
    date_from: date | None,
    date_to: date | None,
) -> list:
    filters = [Notification.user_id == user_id]
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(
            or_(
                Notification.title.ilike(pattern),
                Notification.description.ilike(pattern),
            )
        )
    if category:
        filters.append(Notification.category == category)
    if priority:
        filters.append(Notification.priority == priority)
    if notification_status:
        filters.append(Notification.status == notification_status)
    if date_from:
        filters.append(
            Notification.created_at
            >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        )
    if date_to:
        filters.append(
            Notification.created_at
            < datetime.combine(
                date_to + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
            )
        )
    return filters
