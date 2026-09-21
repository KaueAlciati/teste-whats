from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.models.financial_profile import FinancialProfile
from backend.models.financial_transaction import FinancialTransaction
from backend.models.goal import Goal
from backend.models.goal_contribution import GoalContribution
from backend.schemas.insights import (
    CategoryAmount,
    CategoryChange,
    DeterministicAlert,
    FinancialHealth,
    FinancialPossibility,
    FinancialSummary,
    GoalAnalysis,
    LargestExpense,
    MonthlyAnalysisPoint,
)


ZERO = Decimal("0.00")


@dataclass(frozen=True)
class InsightThresholds:
    significant_expense_increase: Decimal = Decimal("20.00")
    high_income_commitment: Decimal = Decimal("80.00")
    high_category_concentration: Decimal = Decimal("50.00")
    trend_change: Decimal = Decimal("10.00")
    good_health_score: int = 70
    attention_health_score: int = 40


THRESHOLDS = InsightThresholds()


def calculate_financial_summary(
    db: Session,
    *,
    user_id: int,
    current_date: date | None = None,
) -> FinancialSummary:
    reference_date = current_date or date.today()
    current_month = reference_date.replace(day=1)
    previous_month = _shift_month(current_month, -1)
    next_month = _shift_month(current_month, 1)

    transactions = list(
        db.scalars(
            select(FinancialTransaction)
            .options(joinedload(FinancialTransaction.category))
            .where(FinancialTransaction.user_id == user_id)
            .order_by(FinancialTransaction.transaction_date, FinancialTransaction.id)
        )
    )
    current_transactions = [
        item
        for item in transactions
        if current_month <= item.transaction_date < next_month
    ]
    previous_transactions = [
        item
        for item in transactions
        if previous_month <= item.transaction_date < current_month
    ]

    total_income = _sum_type(transactions, "income")
    total_expenses = _sum_type(transactions, "expense")
    current_income = _sum_type(current_transactions, "income")
    current_expenses = _sum_type(current_transactions, "expense")
    previous_expenses = _sum_type(previous_transactions, "expense")
    free_amount = current_income - current_expenses

    committed_percentage = (
        _percentage(current_expenses, current_income)
        if current_income > ZERO
        else None
    )
    expense_change = (
        _percentage(current_expenses - previous_expenses, previous_expenses)
        if previous_expenses > ZERO
        else None
    )

    current_expense_items = [
        item for item in current_transactions if item.type == "expense"
    ]
    category_current = _category_totals(current_expense_items)
    category_previous = _category_totals(
        [item for item in previous_transactions if item.type == "expense"]
    )
    distribution = _category_distribution(category_current, current_expenses)
    category_changes = _category_changes(category_current, category_previous)

    largest = max(
        current_expense_items,
        key=lambda item: item.amount,
        default=None,
    )
    largest_expense = (
        LargestExpense(
            description=largest.description,
            amount=float(largest.amount),
            category=_category_name(largest),
            transaction_date=largest.transaction_date,
        )
        if largest is not None
        else None
    )

    month_buckets = _monthly_buckets(transactions, through=reference_date)
    average_income = _average_bucket(month_buckets, "income")
    average_expenses = _average_bucket(month_buckets, "expense")
    recent_trend = _recent_expense_trend(month_buckets)
    monthly_history = _monthly_history(month_buckets, reference_date)

    goals = list(
        db.scalars(
            select(Goal)
            .where(Goal.user_id == user_id, Goal.status == "active")
            .order_by(Goal.id.desc())
        )
    )
    goal_rows = [_goal_analysis(goal, reference_date) for goal in goals]
    total_saved = sum((goal.current_amount for goal in goals), ZERO)
    total_remaining = sum(
        (max(ZERO, goal.target_amount - goal.current_amount) for goal in goals),
        ZERO,
    )
    contributions = list(
        db.scalars(
            select(GoalContribution).where(GoalContribution.user_id == user_id)
        )
    )
    average_contribution = (
        sum((item.amount for item in contributions), ZERO)
        / Decimal(len(contributions))
        if len(contributions) >= 2
        else None
    )

    return FinancialSummary(
        balance=float(total_income - total_expenses),
        current_month_income=float(current_income),
        current_month_expenses=float(current_expenses),
        free_amount=float(free_amount),
        committed_income_percentage=_optional_float(committed_percentage),
        average_monthly_expenses=_optional_float(average_expenses),
        average_monthly_income=_optional_float(average_income),
        transaction_count=len(transactions),
        largest_expense=largest_expense,
        top_expense_category=(distribution[0].category if distribution else None),
        category_distribution=distribution,
        previous_month_expenses=float(previous_expenses),
        expense_change_percentage=_optional_float(expense_change),
        category_changes=category_changes,
        recent_expense_trend=recent_trend,
        monthly_history=monthly_history,
        active_goals_count=len(goals),
        total_saved_in_goals=float(total_saved),
        total_remaining_in_goals=float(total_remaining),
        goals=goal_rows,
        average_goal_contribution=_optional_float(average_contribution),
        estimated_monthly_savings_capacity=(
            float(max(ZERO, free_amount)) if current_income > ZERO else None
        ),
    )


def build_deterministic_alerts(
    summary: FinancialSummary,
) -> list[DeterministicAlert]:
    alerts: list[DeterministicAlert] = []
    if summary.transaction_count == 0:
        return [
            DeterministicAlert(
                code="insufficient_transactions",
                severity="info",
                title="Comece registrando suas movimentações",
                message=(
                    "Ainda não há transações suficientes para identificar "
                    "padrões financeiros."
                ),
            )
        ]
    if summary.free_amount < 0:
        alerts.append(
            DeterministicAlert(
                code="negative_monthly_balance",
                severity="critical",
                title="Saídas acima das entradas",
                message=(
                    "As despesas registradas neste mês superam as receitas "
                    f"em R$ {abs(summary.free_amount):.2f}."
                ),
            )
        )
    elif summary.current_month_income > 0:
        alerts.append(
            DeterministicAlert(
                code="positive_monthly_surplus",
                severity="positive",
                title="Sobra mensal positiva",
                message=(
                    f"Há R$ {summary.free_amount:.2f} livres entre as receitas "
                    "e despesas registradas neste mês."
                ),
            )
        )
    if (
        summary.committed_income_percentage is not None
        and Decimal(str(summary.committed_income_percentage))
        >= THRESHOLDS.high_income_commitment
    ):
        alerts.append(
            DeterministicAlert(
                code="high_income_commitment",
                severity="attention",
                title="Renda muito comprometida",
                message=(
                    f"{summary.committed_income_percentage:.1f}% das entradas "
                    "do mês estão comprometidas pelas despesas registradas."
                ),
            )
        )
    if (
        summary.expense_change_percentage is not None
        and Decimal(str(summary.expense_change_percentage))
        >= THRESHOLDS.significant_expense_increase
    ):
        alerts.append(
            DeterministicAlert(
                code="expenses_increased",
                severity="attention",
                title="Despesas em alta",
                message=(
                    "As despesas aumentaram "
                    f"{summary.expense_change_percentage:.1f}% em relação ao mês anterior."
                ),
            )
        )
    if (
        summary.category_distribution
        and Decimal(str(summary.category_distribution[0].percentage))
        >= THRESHOLDS.high_category_concentration
    ):
        top = summary.category_distribution[0]
        alerts.append(
            DeterministicAlert(
                code="category_concentration",
                severity="attention",
                title="Gastos concentrados",
                message=(
                    f"{top.category} representa {top.percentage:.1f}% das "
                    "despesas deste mês."
                ),
            )
        )
    for change in summary.category_changes:
        if (
            change.direction == "increased"
            and change.percentage_change is not None
            and Decimal(str(change.percentage_change))
            >= THRESHOLDS.significant_expense_increase
        ):
            alerts.append(
                DeterministicAlert(
                    code=f"category_increase_{change.category.casefold()}",
                    severity="attention",
                    title=f"{change.category} aumentou",
                    message=(
                        f"Os gastos em {change.category} aumentaram "
                        f"{change.percentage_change:.1f}% em relação ao mês anterior."
                    ),
                )
            )
    if summary.active_goals_count == 0:
        alerts.append(
            DeterministicAlert(
                code="no_active_goals",
                severity="info",
                title="Nenhuma meta ativa",
                message="Criar uma meta ajuda a dar destino para a sobra mensal.",
            )
        )
    capacity = summary.estimated_monthly_savings_capacity
    if capacity is not None:
        for goal in summary.goals:
            if (
                goal.required_monthly_amount is not None
                and goal.required_monthly_amount > capacity
            ):
                alerts.append(
                    DeterministicAlert(
                        code=f"goal_pace_{goal.id}",
                        severity="attention",
                        title=f"Ritmo da meta {goal.name}",
                        message=(
                            f"A meta exige cerca de R$ {goal.required_monthly_amount:.2f} "
                            "por mês, acima da capacidade estimada com os dados atuais."
                        ),
                    )
                )
    return alerts


def calculate_financial_health(summary: FinancialSummary) -> FinancialHealth:
    if summary.transaction_count == 0:
        return FinancialHealth(
            level="attention",
            score=50,
            explanation="Ainda faltam movimentações para uma avaliação confiável.",
        )
    score = 100
    reasons: list[str] = []
    if summary.free_amount < 0:
        score -= 40
        reasons.append("as despesas do mês superam as entradas")
    if (
        summary.committed_income_percentage is not None
        and Decimal(str(summary.committed_income_percentage))
        >= THRESHOLDS.high_income_commitment
    ):
        score -= 25
        reasons.append("a renda está muito comprometida")
    if (
        summary.expense_change_percentage is not None
        and Decimal(str(summary.expense_change_percentage))
        >= THRESHOLDS.significant_expense_increase
    ):
        score -= 15
        reasons.append("as despesas cresceram em relação ao mês anterior")
    if summary.active_goals_count == 0:
        score -= 5
    score = max(0, min(100, score))
    if score >= THRESHOLDS.good_health_score:
        level = "good"
        explanation = "Os registros atuais indicam equilíbrio financeiro."
    elif score >= THRESHOLDS.attention_health_score:
        level = "attention"
        explanation = "Há pontos que merecem acompanhamento: " + "; ".join(reasons)
    else:
        level = "critical"
        explanation = "A situação exige prioridade: " + "; ".join(reasons)
    return FinancialHealth(level=level, score=score, explanation=explanation)


def build_financial_possibilities(
    profile: FinancialProfile,
    summary: FinancialSummary,
) -> list[FinancialPossibility]:
    possibilities: list[FinancialPossibility] = []
    if profile.has_debts:
        possibilities.append(
            FinancialPossibility(
                title="Organização e redução de dívidas",
                objective="Liberar orçamento antes de assumir riscos financeiros.",
                horizon="Curto prazo",
                liquidity="Preservar caixa para pagamentos e imprevistos.",
                risk="Baixo",
                care="Compare custos, prazos e condições antes de renegociar.",
            )
        )
    if profile.main_goal == "emergency_reserve" or profile.liquidity_need == "high":
        possibilities.append(
            FinancialPossibility(
                title="Reserva com alta liquidez",
                objective="Manter recursos acessíveis para emergências.",
                horizon="Curto prazo",
                liquidity="Alta",
                risk="Baixo",
                care="Observe segurança, liquidez e custos; rentabilidade não é garantida.",
            )
        )
    if profile.investment_horizon in {"up_to_6_months", "up_to_1_year"}:
        possibilities.append(
            FinancialPossibility(
                title="Alternativas conservadoras de curto prazo",
                objective="Organizar dinheiro destinado a objetivos próximos.",
                horizon="Até 1 ano",
                liquidity="Compatível com a data do objetivo",
                risk="Baixo a moderado",
                care="Evite prazos de resgate posteriores à necessidade do dinheiro.",
            )
        )
    else:
        possibilities.append(
            FinancialPossibility(
                title="Diversificação educacional de longo prazo",
                objective="Distribuir riscos para objetivos mais distantes.",
                horizon="Médio a longo prazo",
                liquidity="Pode ser menor conforme o objetivo",
                risk=profile.risk_profile,
                care=(
                    "Conheça volatilidade, custos e riscos antes de qualquer decisão; "
                    "não concentre todo o patrimônio em uma única categoria."
                ),
            )
        )
    if summary.estimated_monthly_savings_capacity == 0:
        possibilities.append(
            FinancialPossibility(
                title="Primeiro passo: recuperar capacidade de poupança",
                objective="Criar espaço no orçamento antes de direcionar novos aportes.",
                horizon="Imediato",
                liquidity="Não se aplica",
                risk="Não se aplica",
                care="Use os registros reais para revisar despesas sem comprometer necessidades.",
            )
        )
    return possibilities[:4]


def _sum_type(items: list[FinancialTransaction], transaction_type: str) -> Decimal:
    return sum(
        (item.amount for item in items if item.type == transaction_type),
        ZERO,
    )


def _category_name(transaction: FinancialTransaction) -> str:
    return transaction.category.name if transaction.category is not None else "Sem categoria"


def _category_totals(items: list[FinancialTransaction]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for item in items:
        name = _category_name(item)
        totals[name] = totals.get(name, ZERO) + item.amount
    return totals


def _category_distribution(
    totals: dict[str, Decimal],
    total_expenses: Decimal,
) -> list[CategoryAmount]:
    return [
        CategoryAmount(
            category=category,
            amount=float(amount),
            percentage=float(_percentage(amount, total_expenses)),
        )
        for category, amount in sorted(
            totals.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        if total_expenses > ZERO
    ]


def _category_changes(
    current: dict[str, Decimal],
    previous: dict[str, Decimal],
) -> list[CategoryChange]:
    changes: list[CategoryChange] = []
    for category in sorted(set(current) | set(previous)):
        current_amount = current.get(category, ZERO)
        previous_amount = previous.get(category, ZERO)
        difference = current_amount - previous_amount
        percentage = (
            _percentage(difference, previous_amount)
            if previous_amount > ZERO
            else None
        )
        direction = (
            "increased" if difference > ZERO else "decreased" if difference < ZERO else "stable"
        )
        changes.append(
            CategoryChange(
                category=category,
                current_amount=float(current_amount),
                previous_amount=float(previous_amount),
                difference=float(difference),
                percentage_change=_optional_float(percentage),
                direction=direction,
            )
        )
    return sorted(changes, key=lambda item: abs(item.difference), reverse=True)


def _monthly_buckets(
    transactions: list[FinancialTransaction],
    *,
    through: date,
) -> dict[tuple[int, int], dict[str, Decimal]]:
    buckets: dict[tuple[int, int], dict[str, Decimal]] = {}
    for item in transactions:
        if item.transaction_date > through:
            continue
        key = (item.transaction_date.year, item.transaction_date.month)
        bucket = buckets.setdefault(key, {"income": ZERO, "expense": ZERO})
        bucket[item.type] += item.amount
    return buckets


def _average_bucket(
    buckets: dict[tuple[int, int], dict[str, Decimal]],
    key: str,
) -> Decimal | None:
    if not buckets:
        return None
    return sum((bucket[key] for bucket in buckets.values()), ZERO) / Decimal(
        len(buckets)
    )


def _recent_expense_trend(
    buckets: dict[tuple[int, int], dict[str, Decimal]],
) -> str | None:
    if len(buckets) < 3:
        return None
    recent_keys = sorted(buckets)[-3:]
    first = buckets[recent_keys[0]]["expense"]
    last = buckets[recent_keys[-1]]["expense"]
    if first <= ZERO:
        return None
    change = _percentage(last - first, first)
    if change >= THRESHOLDS.trend_change:
        return "increasing"
    if change <= -THRESHOLDS.trend_change:
        return "decreasing"
    return "stable"


def _monthly_history(
    buckets: dict[tuple[int, int], dict[str, Decimal]],
    reference_date: date,
) -> list[MonthlyAnalysisPoint]:
    starts = [_shift_month(reference_date.replace(day=1), offset) for offset in range(-5, 1)]
    return [
        MonthlyAnalysisPoint(
            month=f"{month.year:04d}-{month.month:02d}",
            income=float(buckets.get((month.year, month.month), {}).get("income", ZERO)),
            expense=float(buckets.get((month.year, month.month), {}).get("expense", ZERO)),
        )
        for month in starts
    ]


def _goal_analysis(goal: Goal, reference_date: date) -> GoalAnalysis:
    remaining = max(ZERO, goal.target_amount - goal.current_amount)
    progress = min(Decimal("100.00"), _percentage(goal.current_amount, goal.target_amount))
    months = _months_until(reference_date, goal.target_date) if goal.target_date else None
    required = remaining / Decimal(months) if months and remaining > ZERO else None
    return GoalAnalysis(
        id=goal.id,
        name=goal.name,
        target_amount=float(goal.target_amount),
        current_amount=float(goal.current_amount),
        remaining_amount=float(remaining),
        progress_percentage=float(progress),
        target_date=goal.target_date,
        required_monthly_amount=_optional_float(required),
    )


def _months_until(start: date, end: date) -> int | None:
    if end <= start:
        return None
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day > start.day:
        months += 1
    return max(1, months)


def _percentage(value: Decimal, denominator: Decimal) -> Decimal:
    if denominator == ZERO:
        return ZERO
    return ((value / denominator) * Decimal("100")).quantize(Decimal("0.01"))


def _optional_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _shift_month(month_start: date, offset: int) -> date:
    absolute_month = month_start.year * 12 + month_start.month - 1 + offset
    year, zero_based_month = divmod(absolute_month, 12)
    return date(year, zero_based_month + 1, 1)
