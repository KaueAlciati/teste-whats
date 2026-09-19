from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.models.financial_transaction import FinancialTransaction
from backend.schemas.dashboard import (
    DashboardResponse,
    MonthlyFlowPoint,
    RecentTransactionResponse,
)
from backend.services.financial_service import (
    calculate_balance,
    calculate_total_by_type,
)


MONTH_NAMES = (
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
)


def get_dashboard_data(
    db: Session,
    *,
    user_id: int,
    current_date: date | None = None,
) -> DashboardResponse:
    reference_date = current_date or date.today()
    month_starts = [
        _shift_month(reference_date.replace(day=1), offset)
        for offset in range(-5, 1)
    ]
    flow_by_month = {
        (month_start.year, month_start.month): {
            "income": Decimal("0.00"),
            "expense": Decimal("0.00"),
        }
        for month_start in month_starts
    }

    flow_rows = db.execute(
        select(
            FinancialTransaction.type,
            FinancialTransaction.amount,
            FinancialTransaction.transaction_date,
        ).where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.transaction_date >= month_starts[0],
        )
    ).all()
    for transaction_type, amount, transaction_date in flow_rows:
        bucket = flow_by_month.get(
            (transaction_date.year, transaction_date.month)
        )
        if bucket is not None:
            bucket[transaction_type] += amount

    recent = list(
        db.scalars(
            select(FinancialTransaction)
            .options(joinedload(FinancialTransaction.category))
            .where(FinancialTransaction.user_id == user_id)
            .order_by(
                FinancialTransaction.transaction_date.desc(),
                FinancialTransaction.id.desc(),
            )
            .limit(5)
        )
    )

    return DashboardResponse(
        balance=float(calculate_balance(db, user_id=user_id)),
        total_income=float(
            calculate_total_by_type(
                db,
                user_id=user_id,
                transaction_type="income",
            )
        ),
        total_expense=float(
            calculate_total_by_type(
                db,
                user_id=user_id,
                transaction_type="expense",
            )
        ),
        monthly_flow=[
            MonthlyFlowPoint(
                name=MONTH_NAMES[month_start.month - 1],
                income=flow_by_month[(month_start.year, month_start.month)][
                    "income"
                ],
                expense=flow_by_month[(month_start.year, month_start.month)][
                    "expense"
                ],
            )
            for month_start in month_starts
        ],
        recent_transactions=[
            RecentTransactionResponse(
                id=transaction.id,
                description=transaction.description,
                amount=float(transaction.amount),
                type=transaction.type,
                category=(
                    transaction.category.name
                    if transaction.category is not None
                    else "Sem categoria"
                ),
                date=transaction.transaction_date,
            )
            for transaction in recent
        ],
    )


def _shift_month(month_start: date, offset: int) -> date:
    absolute_month = month_start.year * 12 + month_start.month - 1 + offset
    year, zero_based_month = divmod(absolute_month, 12)
    return date(year, zero_based_month + 1, 1)
