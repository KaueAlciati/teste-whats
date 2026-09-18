from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


FinancialAction = Literal[
    "create_expense",
    "create_income",
    "query_balance",
    "query_expenses",
    "query_income",
    "correct_last_transaction",
    "cancel_last_transaction",
    "unknown",
]

FinancialTransactionType = Literal["expense", "income"]

FinancialPeriod = Literal[
    "today",
    "yesterday",
    "current_week",
    "current_month",
    "previous_month",
    "all",
]


class FinancialIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: FinancialAction
    amount: float | None = None
    description: str | None = None
    category: str | None = None
    transaction_date: str | None = None
    payment_method: str | None = None
    type: FinancialTransactionType | None = None
    period: FinancialPeriod | None = None
    needs_clarification: bool
    clarification_question: str | None = None
    confidence: float

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, amount: float | None) -> float | None:
        if amount is not None and amount <= 0:
            raise ValueError("amount deve ser positivo")
        return amount

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, confidence: float) -> float:
        if not 0 <= confidence <= 1:
            raise ValueError("confidence deve estar entre 0 e 1")
        return confidence
