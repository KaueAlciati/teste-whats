from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


MainGoal = Literal[
    "emergency_reserve",
    "pay_debts",
    "purchase_goal",
    "organize_finances",
    "invest_future",
    "grow_wealth",
]
InvestmentHorizon = Literal[
    "up_to_6_months",
    "up_to_1_year",
    "one_to_three_years",
    "three_to_five_years",
    "more_than_five_years",
]
RiskProfile = Literal["conservative", "moderate", "aggressive"]
LiquidityNeed = Literal["high", "medium", "low"]
IncomeType = Literal["fixed", "variable", "mixed"]
MainPriority = Literal[
    "reduce_expenses",
    "organize_budget",
    "achieve_goals",
    "start_investing",
    "increase_savings",
]


class FinancialProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_goal: MainGoal
    investment_horizon: InvestmentHorizon
    risk_profile: RiskProfile
    liquidity_need: LiquidityNeed
    has_debts: bool
    income_type: IncomeType
    main_priority: MainPriority


class FinancialProfileResponse(FinancialProfileWrite):
    id: int
    onboarding_completed: bool
    created_at: datetime
    updated_at: datetime


class FinancialProfileState(BaseModel):
    onboarding_completed: bool
    profile: FinancialProfileResponse | None


class CategoryAmount(BaseModel):
    category: str
    amount: float
    percentage: float


class CategoryChange(BaseModel):
    category: str
    current_amount: float
    previous_amount: float
    difference: float
    percentage_change: float | None
    direction: Literal["increased", "decreased", "stable"]


class LargestExpense(BaseModel):
    description: str
    amount: float
    category: str
    transaction_date: date


class MonthlyAnalysisPoint(BaseModel):
    month: str
    income: float
    expense: float


class GoalAnalysis(BaseModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    remaining_amount: float
    progress_percentage: float
    target_date: date | None
    required_monthly_amount: float | None


class FinancialSummary(BaseModel):
    balance: float
    current_month_income: float
    current_month_expenses: float
    free_amount: float
    committed_income_percentage: float | None
    average_monthly_expenses: float | None
    average_monthly_income: float | None
    transaction_count: int
    largest_expense: LargestExpense | None
    top_expense_category: str | None
    category_distribution: list[CategoryAmount]
    previous_month_expenses: float
    expense_change_percentage: float | None
    category_changes: list[CategoryChange]
    recent_expense_trend: Literal["increasing", "decreasing", "stable"] | None
    monthly_history: list[MonthlyAnalysisPoint]
    active_goals_count: int
    total_saved_in_goals: float
    total_remaining_in_goals: float
    goals: list[GoalAnalysis]
    average_goal_contribution: float | None
    estimated_monthly_savings_capacity: float | None


class DeterministicAlert(BaseModel):
    code: str
    severity: Literal["positive", "attention", "critical", "info"]
    title: str
    message: str


class FinancialHealth(BaseModel):
    level: Literal["good", "attention", "critical"]
    score: int
    explanation: str


class FinancialPossibility(BaseModel):
    title: str
    objective: str
    horizon: str
    liquidity: str
    risk: str
    care: str


class AIInsightsContent(BaseModel):
    financial_summary: str
    positive_points: list[str]
    attention_points: list[str]
    improvements: list[str]
    cut_suggestions: list[str]
    prioritization: str
    goals_analysis: str
    next_steps: list[str]


class AIInsightsState(BaseModel):
    available: bool
    cached: bool
    generated_at: datetime | None
    message: str | None
    content: AIInsightsContent | None


class MarketAnalysisState(BaseModel):
    available: bool
    message: str
    updated_at: datetime | None
    sources: list[str]


class InsightsAnalysisResponse(BaseModel):
    generated_at: datetime
    profile: FinancialProfileResponse
    summary: FinancialSummary
    health: FinancialHealth
    alerts: list[DeterministicAlert]
    possibilities: list[FinancialPossibility]
    ai: AIInsightsState
    market: MarketAnalysisState


class DashboardInsightResponse(BaseModel):
    onboarding_completed: bool
    short_insight: str
