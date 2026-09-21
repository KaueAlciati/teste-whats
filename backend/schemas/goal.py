from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    target_date: date | None = None


class GoalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=14,
        decimal_places=2,
    )
    target_date: date | None = None
    status: Literal["active", "completed"] | None = None
    current_amount_delta: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=14,
        decimal_places=2,
    )

    @model_validator(mode="after")
    def require_change(self) -> "GoalUpdate":
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para atualizar")
        nullable_only = {"target_date"}
        for field_name in self.model_fields_set - nullable_only:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} não pode ser nulo")
        return self


class GoalResponse(BaseModel):
    id: int
    goal_name: str
    target: float
    current: float
    missing: float
    percent: float
    deadline: date | None
    completed: bool
