from datetime import date, datetime
from decimal import Decimal
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from backend.models.financial_profile import FinancialProfile
from backend.models.financial_transaction import FinancialTransaction
from backend.models.goal import Goal
from backend.models.user import User
from backend.schemas.natural_intent import NaturalIntentDecision
from backend.services.conversation_service import format_brl
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

    if decision.intent == "consultar_maior_gasto":
        transactions = _transactions(
            db,
            user_id=user.id,
            period=period,
            transaction_type="expense",
        )
        if not transactions:
            return f"Não encontrei despesas {period.label}."
        largest = max(transactions, key=lambda item: item.amount)
        return (
            f"Sua maior despesa {period.label} foi "
            f"{format_brl(largest.amount)} com {largest.description}, "
            f"em {largest.transaction_date.strftime('%d/%m/%Y')}."
        )

    if decision.intent == "consultar_categoria_maior_gasto":
        transactions = _transactions(
            db,
            user_id=user.id,
            period=period,
            transaction_type="expense",
        )
        if not transactions:
            return f"Não encontrei despesas {period.label}."
        totals: dict[str, Decimal] = {}
        for transaction in transactions:
            category = _category_name(transaction)
            totals[category] = totals.get(category, Decimal("0")) + transaction.amount
        category, total = max(totals.items(), key=lambda item: item[1])
        return (
            f"A categoria em que você mais gastou {period.label} foi "
            f"{category}: {format_brl(total)}."
        )

    if decision.intent == "consultar_gasto_categoria":
        category_query = (parameters.category or "").strip()
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
            return f"Não encontrei gastos com {category_query} {period.label}."
        return (
            f"Você gastou {format_brl(total)} com {category_query} "
            f"{period.label}."
        )

    if decision.intent == "consultar_ultimas_transacoes":
        limit = parameters.limit or 5
        transactions = _latest_transactions(
            db,
            user_id=user.id,
            limit=limit,
            transaction_type=parameters.transaction_type,
        )
        if not transactions:
            return "Não encontrei movimentações para mostrar."
        lines = ["Suas movimentações mais recentes:"]
        for item in transactions:
            signal = "-" if item.type == "expense" else "+"
            lines.append(
                f"• {item.transaction_date.strftime('%d/%m')}: "
                f"{item.description} — {signal}{format_brl(item.amount)}"
            )
        return "\n".join(lines)

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
        noun = "gastou" if transaction_type == "expense" else "recebeu"
        return f"Você {noun} {format_brl(total)} {period.label}."

    if decision.intent == "analisar_financas":
        summary = calculate_financial_summary(
            db,
            user_id=user.id,
            current_date=current_date,
        )
        profile = _financial_profile(db, user.id)
        health = calculate_financial_health(summary, profile)
        commitment = (
            f"{summary.committed_income_percentage:.1f}%"
            if summary.committed_income_percentage is not None
            else "indisponível sem renda registrada"
        )
        return (
            f"Sua saúde financeira está em nível {health.level}, com score "
            f"{health.score}/100. Neste mês entraram "
            f"{format_brl(Decimal(str(summary.current_month_income)))} e saíram "
            f"{format_brl(Decimal(str(summary.current_month_expenses)))}. "
            f"Comprometimento da renda: {commitment}. {health.explanation}"
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
        return (
            f'A meta mais próxima é "{goal.name}", com '
            f"{_goal_progress(goal):.0f}% concluída. Faltam "
            f"{format_brl(max(Decimal('0'), goal.target_amount - goal.current_amount))}."
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
) -> list[FinancialTransaction]:
    statement = (
        select(FinancialTransaction)
        .where(FinancialTransaction.user_id == user_id)
        .order_by(
            FinancialTransaction.transaction_date.desc(),
            FinancialTransaction.id.desc(),
        )
        .limit(limit)
    )
    if transaction_type is not None:
        statement = statement.where(FinancialTransaction.type == transaction_type)
    return list(db.scalars(statement))


def _matches_category_or_description(
    transaction: FinancialTransaction,
    query: str,
) -> bool:
    normalized_query = normalize_language(query)
    return normalized_query in normalize_language(_category_name(transaction)) or (
        normalized_query in normalize_language(transaction.description)
    )


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
