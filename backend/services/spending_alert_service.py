from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.financial_transaction import FinancialTransaction
from backend.models.notification import Notification
from backend.models.user import User


ATTENTION_THRESHOLD = Decimal("80")
CRITICAL_THRESHOLD = Decimal("100")
SINGLE_EXPENSE_THRESHOLD = Decimal("30")


def evaluate_spending_alerts(
    db: Session,
    *,
    user_id: int,
    reference_date: date,
) -> list[Notification]:
    user = db.get(User, user_id)
    if user is None or not user.critical_spending_alerts_enabled:
        return []

    period_start = reference_date.replace(day=1)
    period_end = _next_month(period_start)
    income = _monthly_total(
        db,
        user_id=user_id,
        transaction_type="income",
        period_start=period_start,
        period_end=period_end,
    )
    if income <= 0:
        return []

    expenses = _monthly_total(
        db,
        user_id=user_id,
        transaction_type="expense",
        period_start=period_start,
        period_end=period_end,
    )
    period_key = period_start.strftime("%Y-%m")
    created: list[Notification] = []
    expense_ratio = _percentage(expenses, income)

    if expense_ratio >= CRITICAL_THRESHOLD:
        notification = _create_once(
            db,
            user_id=user_id,
            rule_code="monthly_expenses_100",
            period_key=period_key,
            title="Despesas atingiram a renda do mês",
            description=(
                f"As despesas de {period_start.strftime('%m/%Y')} chegaram a "
                f"{_format_percentage(expense_ratio)} da renda registrada."
            ),
            priority="urgent",
            data={
                "rule": "monthly_expenses_100",
                "period": period_key,
                "percentage": float(expense_ratio),
            },
        )
        if notification is not None:
            created.append(notification)
    elif expense_ratio >= ATTENTION_THRESHOLD:
        notification = _create_once(
            db,
            user_id=user_id,
            rule_code="monthly_expenses_80",
            period_key=period_key,
            title="Atenção ao orçamento mensal",
            description=(
                f"As despesas de {period_start.strftime('%m/%Y')} chegaram a "
                f"{_format_percentage(expense_ratio)} da renda registrada."
            ),
            priority="high",
            data={
                "rule": "monthly_expenses_80",
                "period": period_key,
                "percentage": float(expense_ratio),
            },
        )
        if notification is not None:
            created.append(notification)

    largest_expense = db.scalar(
        select(FinancialTransaction)
        .where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.type == "expense",
            FinancialTransaction.transaction_date >= period_start,
            FinancialTransaction.transaction_date < period_end,
        )
        .order_by(
            FinancialTransaction.amount.desc(),
            FinancialTransaction.id.asc(),
        )
        .limit(1)
    )
    if largest_expense is not None:
        single_ratio = _percentage(largest_expense.amount, income)
        if single_ratio >= SINGLE_EXPENSE_THRESHOLD:
            notification = _create_once(
                db,
                user_id=user_id,
                rule_code="single_expense_30",
                period_key=period_key,
                title="Gasto elevado identificado",
                description=(
                    f'A despesa "{largest_expense.description}" representa '
                    f"{_format_percentage(single_ratio)} da renda registrada "
                    f"em {period_start.strftime('%m/%Y')}."
                ),
                priority="high",
                data={
                    "rule": "single_expense_30",
                    "period": period_key,
                    "percentage": float(single_ratio),
                    "transaction_id": largest_expense.id,
                },
            )
            if notification is not None:
                created.append(notification)

    return created


def _create_once(
    db: Session,
    *,
    user_id: int,
    rule_code: str,
    period_key: str,
    title: str,
    description: str,
    priority: str,
    data: dict,
) -> Notification | None:
    existing_id = db.scalar(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.rule_code == rule_code,
            Notification.period_key == period_key,
        )
    )
    if existing_id is not None:
        return None

    notification = Notification(
        user_id=user_id,
        title=title,
        description=description,
        category="financeiro",
        priority=priority,
        status="unread",
        rule_code=rule_code,
        period_key=period_key,
        action_url="/transactions",
        data=data,
    )
    try:
        with db.begin_nested():
            db.add(notification)
            db.flush()
    except IntegrityError:
        return None
    return notification


def _monthly_total(
    db: Session,
    *,
    user_id: int,
    transaction_type: str,
    period_start: date,
    period_end: date,
) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(FinancialTransaction.amount), 0)).where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.type == transaction_type,
            FinancialTransaction.transaction_date >= period_start,
            FinancialTransaction.transaction_date < period_end,
        )
    )
    return Decimal(str(value))


def _percentage(value: Decimal, total: Decimal) -> Decimal:
    return (value / total * Decimal("100")).quantize(Decimal("0.01"))


def _format_percentage(value: Decimal) -> str:
    return f"{value:.1f}%".replace(".", ",")


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)
