from __future__ import annotations

import calendar
import logging
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from backend.services.db_init import conectar_bd
from backend.services.web_auth_service import WebUser

logger = logging.getLogger(__name__)

UTC_MINUS_3 = timezone(timedelta(hours=-3))


@dataclass(slots=True)
class PeriodWindow:
    value: str
    label: str
    start: datetime
    end: datetime


def _money_value(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _parse_period_value(period: str | None) -> str:
    normalized = (period or "current_month").strip().lower()
    aliases = {
        "hoje": "today",
        "today": "today",
        "esta semana": "current_week",
        "semana atual": "current_week",
        "current_week": "current_week",
        "semana passada": "previous_week",
        "previous_week": "previous_week",
        "este mes": "current_month",
        "esse mes": "current_month",
        "current_month": "current_month",
        "mes atual": "current_month",
        "mês atual": "current_month",
        "mes passado": "previous_month",
        "previous_month": "previous_month",
        "mês passado": "previous_month",
        "este ano": "current_year",
        "esse ano": "current_year",
        "current_year": "current_year",
    }
    return aliases.get(normalized, normalized)


def build_period_window(period: str | None) -> PeriodWindow:
    value = _parse_period_value(period)
    today = datetime.now(UTC_MINUS_3).date()

    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
        return PeriodWindow(
            value="custom",
            label=parsed.strftime("%d/%m/%Y"),
            start=datetime.combine(parsed, time.min, tzinfo=UTC_MINUS_3),
            end=datetime.combine(parsed, time.max, tzinfo=UTC_MINUS_3),
        )
    if len(value) == 7 and value[4] == "-" and value[:4].isdigit():
        year, month = map(int, value.split("-"))
        start_date = date(year, month, 1)
        end_date = date(year, month, calendar.monthrange(year, month)[1])
        return PeriodWindow(
            value="custom",
            label=f"{month:02d}/{year}",
            start=datetime.combine(start_date, time.min, tzinfo=UTC_MINUS_3),
            end=datetime.combine(end_date, time.max, tzinfo=UTC_MINUS_3),
        )

    if value == "today":
        start_date = end_date = today
        label = today.strftime("%d/%m/%Y")
    elif value == "current_week":
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
        label = f"semana de {start_date.strftime('%d/%m')} a {end_date.strftime('%d/%m')}"
    elif value == "previous_week":
        end_date = today - timedelta(days=today.weekday() + 1)
        start_date = end_date - timedelta(days=6)
        label = f"semana de {start_date.strftime('%d/%m')} a {end_date.strftime('%d/%m')}"
    elif value == "previous_month":
        first_current = today.replace(day=1)
        end_date = first_current - timedelta(days=1)
        start_date = end_date.replace(day=1)
        label = start_date.strftime("%m/%Y")
    elif value == "current_year":
        start_date = date(today.year, 1, 1)
        end_date = date(today.year, 12, 31)
        label = str(today.year)
    else:
        start_date = today.replace(day=1)
        end_date = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
        label = today.strftime("%m/%Y")
        value = "current_month"

    return PeriodWindow(
        value=value,
        label=label,
        start=datetime.combine(start_date, time.min, tzinfo=UTC_MINUS_3),
        end=datetime.combine(end_date, time.max, tzinfo=UTC_MINUS_3),
    )


def _previous_window(window: PeriodWindow) -> PeriodWindow:
    if window.value == "today":
        prev_date = (window.start - timedelta(days=1)).date()
        return PeriodWindow(
            value="previous_day",
            label=prev_date.strftime("%d/%m/%Y"),
            start=datetime.combine(prev_date, time.min, tzinfo=UTC_MINUS_3),
            end=datetime.combine(prev_date, time.max, tzinfo=UTC_MINUS_3),
        )
    if window.value == "current_week":
        start_date = (window.start.date() - timedelta(days=7))
        end_date = start_date + timedelta(days=6)
        return PeriodWindow(
            value="previous_week",
            label=f"semana de {start_date.strftime('%d/%m')} a {end_date.strftime('%d/%m')}",
            start=datetime.combine(start_date, time.min, tzinfo=UTC_MINUS_3),
            end=datetime.combine(end_date, time.max, tzinfo=UTC_MINUS_3),
        )
    if window.value == "previous_week":
        start_date = (window.start.date() - timedelta(days=7))
        end_date = start_date + timedelta(days=6)
        return PeriodWindow(
            value="previous_week",
            label=f"semana de {start_date.strftime('%d/%m')} a {end_date.strftime('%d/%m')}",
            start=datetime.combine(start_date, time.min, tzinfo=UTC_MINUS_3),
            end=datetime.combine(end_date, time.max, tzinfo=UTC_MINUS_3),
        )
    if window.value == "current_year":
        start_date = date(window.start.year - 1, 1, 1)
        end_date = date(window.start.year - 1, 12, 31)
        return PeriodWindow(
            value="previous_year",
            label=str(window.start.year - 1),
            start=datetime.combine(start_date, time.min, tzinfo=UTC_MINUS_3),
            end=datetime.combine(end_date, time.max, tzinfo=UTC_MINUS_3),
        )
    # month fallback
    first_current = window.start.date().replace(day=1)
    previous_end = first_current - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    return PeriodWindow(
        value="previous_month",
        label=previous_start.strftime("%m/%Y"),
        start=datetime.combine(previous_start, time.min, tzinfo=UTC_MINUS_3),
        end=datetime.combine(previous_end, time.max, tzinfo=UTC_MINUS_3),
    )


def _format_currency(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _execute_fetchall(schema: str, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(sql.format(schema=schema), params)
        return cursor.fetchall()
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def _execute_fetchone(schema: str, sql: str, params: tuple[Any, ...]) -> Any:
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(sql.format(schema=schema), params)
        return cursor.fetchone()
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def _sum_value(schema: str, table: str, window: PeriodWindow, column: str = "valor") -> float:
    row = _execute_fetchone(
        schema,
        f"SELECT COALESCE(SUM({column}), 0) FROM {{schema}}.{table} WHERE data >= %s AND data <= %s",
        (window.start, window.end),
    )
    return _money_value(row[0] if row else 0)


def _sum_receitas(schema: str, window: PeriodWindow) -> float:
    receitas = _sum_value(schema, "receitas", window)
    salario = _sum_value(schema, "salario", window)
    return receitas + salario


def _sum_pendentes(schema: str, window: PeriodWindow) -> float:
    row = _execute_fetchone(
        schema,
        "SELECT COALESCE(SUM(valor), 0) FROM {schema}.fatura_cartao WHERE COALESCE(data_fim, data_inicio::date) >= %s AND COALESCE(data_fim, data_inicio::date) <= %s",
        (window.start.date(), window.end.date()),
    )
    return _money_value(row[0] if row else 0)


def _get_categories(schema: str, window: PeriodWindow) -> list[dict[str, Any]]:
    rows = _execute_fetchall(
        schema,
        """
        SELECT COALESCE(categoria, 'geral') AS categoria, COALESCE(SUM(valor), 0) AS total
        FROM {schema}.gastos
        WHERE data >= %s AND data <= %s
        GROUP BY COALESCE(categoria, 'geral')
        ORDER BY total DESC, categoria ASC
        LIMIT 6
        """,
        (window.start, window.end),
    )
    total = sum(_money_value(row[1]) for row in rows) or 0.0
    palette = ["#16A34A", "#22C55E", "#0B7A43", "#64D98A", "#86EFAC", "#B7F7CD"]
    items: list[dict[str, Any]] = []
    for index, (categoria, valor) in enumerate(rows):
        amount = _money_value(valor)
        items.append(
            {
                "label": categoria,
                "value": amount,
                "percent": round((amount / total * 100), 1) if total else 0,
                "color": palette[index % len(palette)],
            }
        )
    return items


def _get_cash_flow(schema: str, window: PeriodWindow) -> dict[str, list[float | str]]:
    rows = _execute_fetchall(
        schema,
        """
        SELECT day, SUM(income) AS income, SUM(expense) AS expense
        FROM (
            SELECT DATE_TRUNC('day', data)::date AS day, valor AS income, 0::numeric AS expense
            FROM {schema}.receitas
            WHERE data >= %s AND data <= %s
            UNION ALL
            SELECT DATE_TRUNC('day', data)::date AS day, valor AS income, 0::numeric AS expense
            FROM {schema}.salario
            WHERE data >= %s AND data <= %s
            UNION ALL
            SELECT DATE_TRUNC('day', data)::date AS day, 0::numeric AS income, valor AS expense
            FROM {schema}.gastos
            WHERE data >= %s AND data <= %s
        ) flows
        GROUP BY day
        ORDER BY day ASC
        """,
        (window.start, window.end, window.start, window.end, window.start, window.end),
    )
    labels = [row[0].strftime("%d/%m") if hasattr(row[0], "strftime") else str(row[0]) for row in rows]
    income = [_money_value(row[1]) for row in rows]
    expense = [_money_value(row[2]) for row in rows]
    return {"labels": labels, "income": income, "expense": expense}


def _get_recent_transactions(schema: str, limit: int = 8) -> list[dict[str, Any]]:
    rows = _execute_fetchall(
        schema,
        """
        SELECT kind, happened_at, description, category, payment_method, amount
        FROM (
            SELECT 'expense'::text AS kind, data AS happened_at, descricao AS description, categoria AS category, meio_pagamento AS payment_method, valor AS amount
            FROM {schema}.gastos
            UNION ALL
            SELECT 'income'::text AS kind, data AS happened_at, descricao AS description, origem AS category, 'pix'::text AS payment_method, valor AS amount
            FROM {schema}.receitas
            UNION ALL
            SELECT 'salary'::text AS kind, data AS happened_at, 'Salário'::text AS description, 'salário'::text AS category, 'transferência'::text AS payment_method, valor AS amount
            FROM {schema}.salario
        ) all_tx
        ORDER BY happened_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [
        {
            "id": f"{kind}-{index}",
            "type": "entrada" if kind in {"income", "salary"} else "saída",
            "kind": kind,
            "date": happened_at.isoformat() if hasattr(happened_at, "isoformat") else str(happened_at),
            "description": description,
            "category": category or "geral",
            "payment_method": payment_method or "não informado",
            "amount": _money_value(amount),
        }
        for index, (kind, happened_at, description, category, payment_method, amount) in enumerate(rows, start=1)
    ]


def _get_reminders(schema: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = _execute_fetchall(
        schema,
        """
        SELECT id, mensagem, cron, data_inclusao
        FROM {schema}.lembretes
        ORDER BY data_inclusao DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [
        {
            "id": row[0],
            "message": row[1],
            "cron": row[2],
            "created_at": row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3]),
        }
        for row in rows
    ]


def _compare(current: float, previous: float) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


def _build_summary_text(current: dict[str, float], previous: dict[str, float], categories: list[dict[str, Any]], period_label: str) -> dict[str, Any]:
    top_category = categories[0] if categories else None
    income_trend = _compare(current["income"], previous["income"])
    expense_trend = _compare(current["expense"], previous["expense"])
    balance_trend = _compare(current["balance"], previous["balance"])
    lines = [f"Resumo de {period_label}."]

    if current["expense"] > current["income"]:
        lines.append("As saídas estão acima das entradas neste período, então vale revisar os principais centros de custo.")
    else:
        lines.append("Suas entradas cobriram as saídas no período analisado.")

    if top_category:
        lines.append(f"A categoria que mais pesou foi {top_category['label']} com {_format_currency(top_category['value'])}.")

    if balance_trend:
        direction = "melhorou" if balance_trend > 0 else "piorou"
        lines.append(f"O saldo {direction} {abs(balance_trend):.1f}% em relação ao período anterior.")

    return {
        "title": "Resumo financeiro automático",
        "text": " ".join(lines),
        "highlights": [
            f"Entradas: {_format_currency(current['income'])} ({income_trend:+.1f}%)",
            f"Saídas: {_format_currency(current['expense'])} ({expense_trend:+.1f}%)",
            f"Saldo: {_format_currency(current['balance'])} ({balance_trend:+.1f}%)",
        ],
    }


def build_dashboard_snapshot(user: WebUser, period: str | None = None) -> dict[str, Any]:
    schema = user.schema_user
    if not schema:
        raise ValueError("Usuário sem schema financeiro vinculado.")

    current_window = build_period_window(period)
    previous_window = _previous_window(current_window)

    current_income = _sum_receitas(schema, current_window)
    current_expense = _sum_value(schema, "gastos", current_window)
    current_pending = _sum_pendentes(schema, current_window)
    current_balance = current_income - current_expense
    projected_balance = current_balance - current_pending

    previous_income = _sum_receitas(schema, previous_window)
    previous_expense = _sum_value(schema, "gastos", previous_window)
    previous_balance = previous_income - previous_expense

    categories = _get_categories(schema, current_window)
    cash_flow = _get_cash_flow(schema, current_window)
    recent_transactions = _get_recent_transactions(schema)
    reminders = _get_reminders(schema)
    summary = _build_summary_text(
        {
            "income": current_income,
            "expense": current_expense,
            "balance": projected_balance,
        },
        {
            "income": previous_income,
            "expense": previous_expense,
            "balance": previous_balance,
        },
        categories,
        current_window.label,
    )

    return {
        "user": {
            "id": user.id,
            "name": user.display_name,
            "email": user.email,
            "phone": user.telefone,
            "avatar": user.web_avatar_url,
            "role": user.web_role,
        },
        "period": {
            "value": current_window.value,
            "label": current_window.label,
            "start": current_window.start.isoformat(),
            "end": current_window.end.isoformat(),
        },
        "cards": {
            "balance": {
                "value": projected_balance,
                "previous": previous_balance,
                "comparison": _compare(projected_balance, previous_balance),
            },
            "income": {
                "value": current_income,
                "previous": previous_income,
                "comparison": _compare(current_income, previous_income),
            },
            "expense": {
                "value": current_expense,
                "previous": previous_expense,
                "comparison": _compare(current_expense, previous_expense),
            },
            "pending_invoice": {
                "value": current_pending,
                "comparison": 0.0,
            },
        },
        "charts": {
            "categories": categories,
            "cash_flow": cash_flow,
        },
        "recent_transactions": recent_transactions,
        "reminders": reminders,
        "goals": [],
        "ai_summary": summary,
    }


def build_dashboard_section(user: WebUser, section: str, period: str | None = None) -> dict[str, Any]:
    data = build_dashboard_snapshot(user, period)
    if section == "categories":
        return {"success": True, "data": data["charts"]["categories"], "message": None}
    if section == "cash-flow":
        return {"success": True, "data": data["charts"]["cash_flow"], "message": None}
    if section == "recent-transactions":
        return {"success": True, "data": data["recent_transactions"], "message": None}
    if section == "ai-summary":
        return {"success": True, "data": data["ai_summary"], "message": None}
    return {"success": True, "data": data, "message": None}
