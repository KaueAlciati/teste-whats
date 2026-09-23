from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    critical_spending_alerts_enabled: bool


class SettingsResponse(BaseModel):
    user_id: int
    currency: str = "BRL"
    locale: str = "pt-BR"
    theme: str = "dark"
    notifications_enabled: bool = True
    ai_enabled: bool = True
    critical_spending_alerts_enabled: bool
    updated_at: datetime
