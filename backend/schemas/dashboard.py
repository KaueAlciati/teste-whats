from datetime import date
from typing import Literal

from pydantic import BaseModel


class MonthlyFlowPoint(BaseModel):
    name: str
    income: float
    expense: float


class RecentTransactionResponse(BaseModel):
    id: int
    description: str
    amount: float
    type: Literal["income", "expense"]
    category: str
    date: date


class DashboardResponse(BaseModel):
    balance: float
    total_income: float
    total_expense: float
    monthly_flow: list[MonthlyFlowPoint]
    recent_transactions: list[RecentTransactionResponse]
