from datetime import datetime
from typing import Literal

from pydantic import BaseModel


NotificationCategory = Literal[
    "financeiro",
    "sistema",
    "ia",
    "seguranca",
    "atualizacoes",
    "lembretes",
]
NotificationPriority = Literal["low", "normal", "high", "urgent"]
NotificationStatus = Literal["unread", "read"]


class NotificationResponse(BaseModel):
    id: int
    title: str
    description: str | None
    category: NotificationCategory
    priority: NotificationPriority
    status: NotificationStatus
    created_at: datetime
    read_at: datetime | None
    action_url: str | None
    metadata: dict | None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    page: int
    page_size: int
    total: int
