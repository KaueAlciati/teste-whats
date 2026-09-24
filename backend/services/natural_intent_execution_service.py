import re
from datetime import date, datetime
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.models.category import Category
from backend.models.financial_profile import FinancialProfile
from backend.models.financial_transaction import FinancialTransaction
from backend.models.goal import Goal
from backend.models.user import User
from backend.schemas.natural_intent import NaturalIntentDecision
from backend.services.conversation_service import (
    format_brl,
    format_category_expenses,
    format_empty_result,
    format_financial_analysis,
    format_goal_progress,
    format_largest_expense,
    format_latest_transactions,
    format_period_name,
    format_period_total,
    format_top_expense_category,
)
from backend.services.goal_context_service import get_selected_goal
from backend.services.goal_contribution_service import list_goal_contributions
from backend.services.goal_service import list_goals
from backend.services.insights_calculation_service import (
    build_deterministic_alerts,
    build_financial_possibilities,
    calculate_financial_health,
    calculate_financial_summary,
)
from backend.services.natural_period_service import (
    NaturalPeriod,
    normalize_language,
    resolve_natural_period,
)


CATEGORY_MATCH_THRESHOLD = 0.86


def execute_natural_intent(
    db: Session,
    *,
    user: User,
    decision: NaturalIntentDecision,
    original_text: str,
    current_date: date,
    current_time: datetime,
) -> str:
    parameters = decision.parameters
    period = resolve_natural_period(
        original_text,
        current_date=current_date,
        period_hint=parameters.period,
        month_hint=parameters.month,
        default="all",
    )
    if not period.is_valid:
        return "Não consegui entender essa data. Pode informar uma data válida?"

    period_name = format_period_name(
        start_date=period.start_date,
        end_date=period.end_date,
        current_date=current_date,
        fallback=period.label,
    )

    if decision.intent == "consultar_maior_gasto":
        transactions = _transactions(
            db,
            user_id=user.id,
            period=period,
            transaction_type="expense",
        )
        if not transactions:
            return format_empty_result(
                title=f"Maior gasto — {period_name}",
                message="Nenhuma despesa encontrada nesse período.",
            )
        largest = max(transactions, key=lambda item: item.amount)
        return format_largest_expense(
            amount=largest.amount,
            description=largest.description,
            transaction_date=largest.transaction_date,
            period_name=period_name,
        )

    if decision.intent == "consultar_categoria_maior_gasto":
        transactions = _transactions(
            db,
            user_id=user.id,
            period=period,
            transaction_type="expense",
        )
        if not transactions:
            return format_empty_result(
                title=f"Onde você mais gastou — {period_name}",
                message="Nenhuma despesa encontrada nesse período.",
            )
        totals: dict[str, Decimal] = {}
        for transaction in transactions:
            category = _category_name(transaction)
            totals[category] = totals.get(category, Decimal("0")) + transaction.amount
        category, total = max(totals.items(), key=lambda item: item[1])
        return format_top_expense_category(
            category=category,
            total=total,
            period_name=period_name,
        )

    if decision.intent == "consultar_gasto_categoria":
        category_query = (parameters.category or "").strip()
        if not _category_query_is_confident(
            db,
            user_id=user.id,
            query=category_query,
        ):
            return (
                "Não encontrei essa categoria com confiança. "
                "Qual categoria você quer consultar?"
            )
        transactions = _transactions(
            db,
            user_id=user.id,
            period=period,
            transaction_type="expense",
        )
        matches = [
            item
            for item in transactions
            if _matches_category_or_description(item, category_query)
        ]
        total = sum((item.amount for item in matches), Decimal("0"))
        if not matches:
            return format_empty_result(
                title=f"Gastos com {category_query} — {period_name}",
                message="Nenhuma despesa encontrada nesse período.",
            )
        return format_category_expenses(
            category=category_query,
            total=total,
            period_name=period_name,
        )

    if decision.intent == "consultar_ultimas_transacoes":
        limit = parameters.limit or 5
        largest_first = bool(
            re.search(
                r"\bmaiores?\s+(?:gastos?|despesas?)\b",
                normalize_language(original_text),
            )
        )
        transactions = _latest_transactions(
            db,
            user_id=user.id,
            limit=limit,
            transaction_type=parameters.transaction_type,
            period=period,
            largest_first=largest_first,
        )
        if not transactions:
            return format_empty_result(
                title=(
                    f"Movimentações — {period_name}"
                    if period.key != "all"
                    else "Movimentações recentes"
                ),
                message="Nenhuma movimentação encontrada.",
            )
        return format_latest_transactions(
            transactions=[
                (item.transaction_date, item.description, item.amount, item.type)
                for item in transactions
            ],
            requested_limit=limit,
            transaction_type=parameters.transaction_type,
            period_name=period_name if period.key != "all" else None,
            largest_first=largest_first,
        )

    if decision.intent in {"consultar_gastos_periodo", "consultar_receitas_periodo"}:
        transaction_type = (
            "expense"
            if decision.intent == "consultar_gastos_periodo"
            else "income"
        )
        transactions = _transactions(
            db,
            user_id=user.id,
            period=period,
            transaction_type=transaction_type,
        )
        total = sum((item.amount for item in transactions), Decimal("0"))
        displayed_transactions = (
            [
                (item.transaction_date, item.description, item.amount)
                for item in transactions
            ]
            if period.start_date is not None and period.start_date == period.end_date
            else None
        )
        return format_period_total(
            transaction_type=transaction_type,
            total=total,
            period_name=period_name,
            transactions=displayed_transactions,
        )

    if decision.intent == "analisar_financas":
        summary = calculate_financial_summary(
            db,
            user_id=user.id,
            current_date=current_date,
        )
        profile = _financial_profile(db, user.id)
        health = calculate_financial_health(summary, profile)
        return format_financial_analysis(
            income=Decimal(str(summary.current_month_income)),
            expenses=Decimal(str(summary.current_month_expenses)),
            free_amount=Decimal(str(summary.free_amount)),
            committed_percentage=summary.committed_income_percentage,
            score=health.score,
            level=health.level,
            explanation=health.explanation,
            period_name=format_period_name(
                start_date=current_date.replace(day=1),
                end_date=current_date,
                current_date=current_date,
                fallback="neste mês",
            ),
        )

    if decision.intent == "sugerir_melhorias_financeiras":
        summary = calculate_financial_summary(
            db,
            user_id=user.id,
            current_date=current_date,
        )
        profile = _financial_profile(db, user.id)
        suggestions = [alert.message for alert in build_deterministic_alerts(summary)]
        if profile is not None:
            suggestions.extend(
                possibility.care
                for possibility in build_financial_possibilities(profile, summary)
            )
        if not suggestions:
            return "Ainda preciso de mais movimentações para sugerir melhorias úteis."
        lines = ["Com base nos seus dados atuais, priorize:"]
        lines.extend(f"• {item}" for item in suggestions[:3])
        return "\n".join(lines)

    if decision.intent == "consultar_meta_mais_proxima":
        goals = [goal for goal in list_goals(db, user_id=user.id) if goal.status == "active"]
        if not goals:
            return "Você não tem metas ativas no momento."
        goal = max(goals, key=_goal_progress)
        return format_goal_progress(
            name=goal.name,
            current_amount=goal.current_amount,
            target_amount=goal.target_amount,
            progress=_goal_progress(goal),
        )

    if decision.intent == "consultar_status_metas":
        goals = list_goals(db, user_id=user.id)
        if not goals:
            return "Você ainda não tem metas cadastradas."
        lines = ["Status das suas metas:"]
        for goal in goals[:10]:
            lines.append(
                f'• {goal.name}: {_goal_progress(goal):.0f}% — faltam '
                f"{format_brl(max(Decimal('0'), goal.target_amount - goal.current_amount))}"
            )
        return "\n".join(lines)

    if decision.intent == "extrato_meta":
        goal = _resolve_goal(
            db,
            user_id=user.id,
            name=parameters.goal_name,
            current_time=current_time,
        )
        if goal is None:
            return "Não encontrei essa meta. Qual meta você quer consultar?"
        contributions = list_goal_contributions(
            db,
            goal_id=goal.id,
            user_id=user.id,
        )
        if not contributions:
            return f'A meta "{goal.name}" ainda não possui aportes.'
        lines = [f'Aportes da meta "{goal.name}":']
        lines.extend(
            f"• {item.created_at.strftime('%d/%m/%Y')}: {format_brl(item.amount)}"
            for item in contributions[:10]
        )
        return "\n".join(lines)

    return (
        "Não consegui entender exatamente o que você quer consultar. Posso te "
        "ajudar com saldo, gastos, receitas, metas, extrato ou análise das suas finanças."
    )


def _transactions(
    db: Session,
    *,
    user_id: int,
    period: NaturalPeriod,
    transaction_type: str,
) -> list[FinancialTransaction]:
    statement = (
        select(FinancialTransaction)
        .options(joinedload(FinancialTransaction.category))
        .where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.type == transaction_type,
        )
        .order_by(
            FinancialTransaction.transaction_date.desc(),
            FinancialTransaction.id.desc(),
        )
    )
    if period.start_date is not None:
        statement = statement.where(
            FinancialTransaction.transaction_date >= period.start_date
        )
    if period.end_date is not None:
        statement = statement.where(
            FinancialTransaction.transaction_date <= period.end_date
        )
    return list(db.scalars(statement))


def _latest_transactions(
    db: Session,
    *,
    user_id: int,
    limit: int,
    transaction_type: str | None,
    period: NaturalPeriod,
    largest_first: bool = False,
) -> list[FinancialTransaction]:
    statement = (
        select(FinancialTransaction)
        .where(FinancialTransaction.user_id == user_id)
    )
    if largest_first:
        statement = statement.order_by(
            FinancialTransaction.amount.desc(),
            FinancialTransaction.transaction_date.desc(),
            FinancialTransaction.id.desc(),
        )
    else:
        statement = statement.order_by(
            FinancialTransaction.transaction_date.desc(),
            FinancialTransaction.id.desc(),
        )
    if transaction_type is not None:
        statement = statement.where(FinancialTransaction.type == transaction_type)
    if period.start_date is not None:
        statement = statement.where(
            FinancialTransaction.transaction_date >= period.start_date
        )
    if period.end_date is not None:
        statement = statement.where(
            FinancialTransaction.transaction_date <= period.end_date
        )
    return list(db.scalars(statement.limit(limit)))


def _matches_category_or_description(
    transaction: FinancialTransaction,
    query: str,
) -> bool:
    normalized_query = normalize_language(query)
    return _category_match_score(
        normalized_query,
        normalize_language(_category_name(transaction)),
    ) >= CATEGORY_MATCH_THRESHOLD or (
        _category_match_score(
            normalized_query,
            normalize_language(transaction.description),
        )
        >= CATEGORY_MATCH_THRESHOLD
    )


def _category_query_is_confident(
    db: Session,
    *,
    user_id: int,
    query: str,
) -> bool:
    normalized_query = normalize_language(query)
    if not normalized_query:
        return False
    category_names = db.scalars(
        select(Category.name).where(
            Category.type == "expense",
            (Category.user_id.is_(None)) | (Category.user_id == user_id),
        )
    )
    descriptions = db.scalars(
        select(FinancialTransaction.description).where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.type == "expense",
        )
    )
    candidates = {
        normalize_language(candidate)
        for candidate in [*category_names, *descriptions]
        if candidate
    }
    return any(
        _category_match_score(normalized_query, candidate)
        >= CATEGORY_MATCH_THRESHOLD
        for candidate in candidates
    )


def _category_match_score(requested: str, candidate: str) -> float:
    if not requested or not candidate:
        return 0.0
    if requested == candidate:
        return 1.0
    if min(len(requested), len(candidate)) >= 4 and requested in candidate:
        return 0.9
    return SequenceMatcher(None, requested, candidate).ratio()


def _category_name(transaction: FinancialTransaction) -> str:
    return transaction.category.name if transaction.category is not None else "Sem categoria"


def _financial_profile(db: Session, user_id: int) -> FinancialProfile | None:
    return db.scalar(
        select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )


def _goal_progress(goal: Goal) -> Decimal:
    return min(
        Decimal("100"),
        goal.current_amount / goal.target_amount * Decimal("100"),
    )


def _resolve_goal(
    db: Session,
    *,
    user_id: int,
    name: str | None,
    current_time: datetime,
) -> Goal | None:
    if not name:
        return get_selected_goal(db, user_id=user_id, current_time=current_time)
    requested = normalize_language(name)
    goals = list_goals(db, user_id=user_id)
    exact = [goal for goal in goals if normalize_language(goal.name) == requested]
    if exact:
        return exact[0]
    partial = [goal for goal in goals if requested in normalize_language(goal.name)]
    if len(partial) == 1:
        return partial[0]
    ranked = sorted(
        (
            (SequenceMatcher(None, requested, normalize_language(goal.name)).ratio(), goal)
            for goal in goals
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    return ranked[0][1] if ranked and ranked[0][0] >= 0.72 else None
