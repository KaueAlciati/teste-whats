from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


NaturalIntentName = Literal[
    "consultar_maior_gasto",
    "consultar_categoria_maior_gasto",
    "consultar_gasto_categoria",
    "consultar_ultimas_transacoes",
    "consultar_gastos_periodo",
    "consultar_receitas_periodo",
    "analisar_financas",
    "sugerir_melhorias_financeiras",
    "consultar_meta_mais_proxima",
    "consultar_status_metas",
    "extrato_meta",
    "unknown",
]

NaturalPeriodName = Literal[
    "today",
    "yesterday",
    "day_before_yesterday",
    "current_week",
    "previous_week",
    "current_month",
    "previous_month",
    "last_7_days",
    "last_15_days",
    "last_30_days",
    "named_month",
    "specific_day",
    "all",
]


class NaturalIntentParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: NaturalPeriodName | None = None
    month: int | None = None
    category: str | None = None
    limit: int | None = None
    goal_name: str | None = None
    transaction_type: Literal["expense", "income"] | None = None

    @field_validator("month")
    @classmethod
    def validate_month(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 12:
            raise ValueError("month deve estar entre 1 e 12")
        return value

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= 20:
            raise ValueError("limit deve estar entre 1 e 20")
        return value


class NaturalIntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: NaturalIntentName
    confidence: float
    parameters: NaturalIntentParameters
    clarification_question: str | None = None
    candidates: list[NaturalIntentName]

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("confidence deve estar entre 0 e 1")
        return value
