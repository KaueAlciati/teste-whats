from __future__ import annotations

import calendar
import logging
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable

from backend.core.financial_agent import FinancialIntentResult
from backend.core.models import AgentResponse, IncomingMessage, SessionData
from backend.core.sessions import session_store
from backend.services.conversational_ai import gerar_resposta_conversacional
from backend.services.db_init import conectar_bd
from backend.services.email_service import buscar_credenciais_email, formatar_emails_para_whatsapp, get_emails_info, listar_emails_cadastrados
from backend.services.gastos_service import apagar_lembrete, pagar_fatura, registrar_salario, salvar_gasto
from backend.services.report_service import gerar_pdf_financeiro
from backend.services.scheduler import agendar_lembrete_cron
from backend.services.token_service import gerar_token_acesso
from backend.utils import obter_schema_por_telefone

logger = logging.getLogger(__name__)

UTC_MINUS_3 = timezone(timedelta(hours=-3))


def _money(value: float | int | None) -> str:
    return f"R$ {float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _today() -> date:
    return datetime.now(UTC_MINUS_3).date()


def _period_bounds(period: str | None) -> tuple[datetime, datetime, str]:
    period_value = (period or "current_month").strip().lower()
    hoje = _today()

    if period_value in {"today"}:
        return (
            datetime.combine(hoje, time.min, tzinfo=UTC_MINUS_3),
            datetime.combine(hoje, time.max, tzinfo=UTC_MINUS_3),
            hoje.strftime("%d/%m/%Y"),
        )

    if period_value in {"yesterday"}:
        dia = hoje - timedelta(days=1)
        return (
            datetime.combine(dia, time.min, tzinfo=UTC_MINUS_3),
            datetime.combine(dia, time.max, tzinfo=UTC_MINUS_3),
            dia.strftime("%d/%m/%Y"),
        )

    if period_value in {"current_week"}:
        inicio = hoje - timedelta(days=hoje.weekday())
        fim = inicio + timedelta(days=6)
        return (
            datetime.combine(inicio, time.min, tzinfo=UTC_MINUS_3),
            datetime.combine(fim, time.max, tzinfo=UTC_MINUS_3),
            f"semana de {inicio.strftime('%d/%m')} a {fim.strftime('%d/%m')}",
        )

    if period_value in {"previous_week"}:
        fim = hoje - timedelta(days=hoje.weekday() + 1)
        inicio = fim - timedelta(days=6)
        return (
            datetime.combine(inicio, time.min, tzinfo=UTC_MINUS_3),
            datetime.combine(fim, time.max, tzinfo=UTC_MINUS_3),
            f"semana de {inicio.strftime('%d/%m')} a {fim.strftime('%d/%m')}",
        )

    if period_value in {"current_year"}:
        inicio = date(hoje.year, 1, 1)
        fim = date(hoje.year, 12, 31)
        return (
            datetime.combine(inicio, time.min, tzinfo=UTC_MINUS_3),
            datetime.combine(fim, time.max, tzinfo=UTC_MINUS_3),
            str(hoje.year),
        )

    if period_value in {"previous_month"}:
        primeiro_mes_atual = hoje.replace(day=1)
        fim = primeiro_mes_atual - timedelta(days=1)
        inicio = fim.replace(day=1)
        return (
            datetime.combine(inicio, time.min, tzinfo=UTC_MINUS_3),
            datetime.combine(fim, time.max, tzinfo=UTC_MINUS_3),
            inicio.strftime("%m/%Y"),
        )

    if period_value in {"current_month", "this_month", "month"}:
        inicio = hoje.replace(day=1)
        ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
        fim = hoje.replace(day=ultimo_dia)
        return (
            datetime.combine(inicio, time.min, tzinfo=UTC_MINUS_3),
            datetime.combine(fim, time.max, tzinfo=UTC_MINUS_3),
            hoje.strftime("%m/%Y"),
        )

    if len(period_value) == 7 and period_value[4] == "-":
        ano, mes = map(int, period_value.split("-"))
        inicio = date(ano, mes, 1)
        fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
        return (
            datetime.combine(inicio, time.min, tzinfo=UTC_MINUS_3),
            datetime.combine(fim, time.max, tzinfo=UTC_MINUS_3),
            f"{mes:02d}/{ano}",
        )

    if len(period_value) == 10 and period_value[4] == "-" and period_value[7] == "-":
        dia = datetime.strptime(period_value, "%Y-%m-%d").date()
        return (
            datetime.combine(dia, time.min, tzinfo=UTC_MINUS_3),
            datetime.combine(dia, time.max, tzinfo=UTC_MINUS_3),
            dia.strftime("%d/%m/%Y"),
        )

    inicio = hoje.replace(day=1)
    ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
    fim = hoje.replace(day=ultimo_dia)
    return (
        datetime.combine(inicio, time.min, tzinfo=UTC_MINUS_3),
        datetime.combine(fim, time.max, tzinfo=UTC_MINUS_3),
        hoje.strftime("%m/%Y"),
    )


def _session_schema(session: SessionData) -> str | None:
    schema = session.state.get("schema")
    if schema:
        return schema
    return obter_schema_por_telefone(session.user_id)


def _set_financial_context(session: SessionData, intent: str, parameters: dict[str, Any]) -> None:
    session.state["current_domain"] = "financial"
    session.state["current_intent"] = intent
    session.state["last_financial_action"] = intent
    session.state["last_financial_parameters"] = parameters
    session.state["collected_parameters"] = parameters
    session_store.set_financial_context(session.channel, session.user_id, intent=intent, parameters=parameters)


def _ensure_pending(session: SessionData, intent: str, parameters: dict[str, Any], missing_fields: list[str], question: str) -> AgentResponse:
    session_store.set_pending_intent(
        session.channel,
        session.user_id,
        intent,
        parameters=parameters,
        missing_fields=missing_fields,
        clarification_question=question,
    )
    session_store.set_pending_context(
        session.channel,
        session.user_id,
        question=question,
        field=missing_fields[0] if missing_fields else None,
        user_answer=session.state.get("last_user_answer"),
    )
    return AgentResponse(text=question, metadata={"intent": intent, "pending": True, "missing_fields": missing_fields})


def _expense_rows(schema: str, inicio: datetime, fim: datetime) -> list[dict[str, Any]]:
    conn = conectar_bd()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT descricao, valor, categoria, meio_pagamento, data
            FROM {schema}.gastos
            WHERE data >= %s AND data <= %s
            ORDER BY data ASC
            """,
            (inicio, fim),
        )
        rows = cursor.fetchall()
        return [
            {
                "descricao": row[0] or "",
                "valor": float(row[1] or 0),
                "categoria": row[2] or "geral",
                "meio_pagamento": row[3] or "não informado",
                "data": row[4],
            }
            for row in rows
        ]
    finally:
        cursor.close()
        conn.close()


def _income_rows(schema: str, inicio: datetime, fim: datetime) -> list[dict[str, Any]]:
    conn = conectar_bd()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT descricao, valor, origem, data
            FROM {schema}.receitas
            WHERE data >= %s AND data <= %s
            ORDER BY data ASC
            """,
            (inicio, fim),
        )
        rows = cursor.fetchall()
        return [
            {
                "descricao": row[0] or "",
                "valor": float(row[1] or 0),
                "origem": row[2] or "geral",
                "data": row[3],
            }
            for row in rows
        ]
    finally:
        cursor.close()
        conn.close()


def _invoice_rows(schema: str, inicio: datetime, fim: datetime) -> list[tuple[Any, ...]]:
    conn = conectar_bd()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT descricao, valor, categoria, meio_pagamento, parcela, data_inicio, data_fim
            FROM {schema}.fatura_cartao
            WHERE COALESCE(data_inicio, CURRENT_TIMESTAMP) >= %s AND COALESCE(data_inicio, CURRENT_TIMESTAMP) <= %s
            ORDER BY data_inicio ASC
            """,
            (inicio, fim),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def _summarize_expenses(rows: list[dict[str, Any]], periodo_label: str) -> str:
    total = sum(item["valor"] for item in rows)
    categorias = Counter(item["categoria"] for item in rows)
    meios = Counter(item["meio_pagamento"] for item in rows)
    maior = max(rows, key=lambda item: item["valor"], default=None)
    partes = [
        f"Seus gastos de {periodo_label} somam {_money(total)}.",
        f"Encontrei {len(rows)} lançamento(s).",
    ]
    if maior:
        partes.append(f"O maior foi {_money(maior['valor'])} em {maior['categoria']}.")
    if categorias:
        categoria_top, valor_top = max(
            ((cat, sum(item["valor"] for item in rows if item["categoria"] == cat)) for cat in categorias),
            key=lambda item: item[1],
        )
        partes.append(f"A categoria que mais pesou foi {categoria_top} com {_money(valor_top)}.")
    if meios:
        meio_top, valor_meio = max(
            ((meio, sum(item["valor"] for item in rows if item["meio_pagamento"] == meio)) for meio in meios),
            key=lambda item: item[1],
        )
        partes.append(f"O meio de pagamento mais usado foi {meio_top} com {_money(valor_meio)}.")
    if not rows:
        partes.append("Não encontrei lançamentos nesse período.")
    return " ".join(partes)


async def execute_register_expense(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})

    params = dict(result.parameters or {})
    amount = params.get("amount")
    description = params.get("description")
    payment_method = params.get("payment_method") or "não informado"
    missing = [field for field in ("amount", "description") if not params.get(field)]

    if missing:
        question = result.clarification_question or ("Qual foi o valor?" if "amount" in missing else "Com o que foi esse gasto?")
        return _ensure_pending(session, "register_expense", params, missing, question)

    salvar_gasto(description, float(amount), params.get("category") or "geral", payment_method, schema)
    _set_financial_context(session, "register_expense", params)
    return AgentResponse(
        text=f"Pronto, registrei {_money(amount)} de {description} no {payment_method}.",
        metadata={"intent": "register_expense", "amount": float(amount), "description": description, "payment_method": payment_method},
    )


async def execute_register_income(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})

    params = dict(result.parameters or {})
    amount = params.get("amount")
    if amount is None:
        question = result.clarification_question or "Qual foi o valor que entrou?"
        return _ensure_pending(session, "register_income", params, ["amount"], question)

    conn = conectar_bd()
    cursor = conn.cursor()
    try:
        cursor.execute(f"INSERT INTO {schema}.receitas (descricao, valor, origem) VALUES (%s, %s, %s)", (params.get("description") or "receita", float(amount), params.get("origem") or "geral"))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    _set_financial_context(session, "register_income", params)
    return AgentResponse(text=f"Pronto, registrei {_money(amount)} como entrada.", metadata={"intent": "register_income", "amount": float(amount)})


async def execute_register_salary(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})

    params = dict(result.parameters or {})
    amount = params.get("amount")
    if amount is None:
        question = result.clarification_question or "Qual foi o valor do salário?"
        return _ensure_pending(session, "register_salary", params, ["amount"], question)

    response_text = registrar_salario(f"{amount}", schema)
    _set_financial_context(session, "register_salary", params)
    return AgentResponse(text=response_text, metadata={"intent": "register_salary", "amount": float(amount)})


async def execute_get_total_expense(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})

    params = dict(result.parameters or {})
    periodo = params.get("period") or "current_month"
    inicio, fim, label = _period_bounds(periodo)
    rows = _expense_rows(schema, inicio, fim)
    total = sum(item["valor"] for item in rows)
    _set_financial_context(session, "get_total_expense", params)
    return AgentResponse(text=f"Até agora, seus gastos de {label} somam {_money(total)}.", metadata={"intent": "get_total_expense", "period": periodo, "total": float(total)})


async def execute_list_expenses(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})

    params = dict(result.parameters or {})
    periodo = params.get("period") or "current_month"
    inicio, fim, label = _period_bounds(periodo)
    rows = _expense_rows(schema, inicio, fim)
    if not rows:
        return AgentResponse(text=f"Não encontrei gastos em {label}.", metadata={"intent": "list_expenses", "period": periodo})

    linhas = [f"• {item['data'].strftime('%d/%m')} - {_money(item['valor'])} - {item['categoria']} - {item['descricao']}" for item in rows]
    _set_financial_context(session, "list_expenses", params)
    return AgentResponse(text=f"Encontrei {len(rows)} gasto(s) em {label}:\n" + "\n".join(linhas), metadata={"intent": "list_expenses", "period": periodo, "count": len(rows)})


async def execute_get_expense_summary(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})

    params = dict(result.parameters or {})
    periodo = params.get("period") or "current_month"
    inicio, fim, label = _period_bounds(periodo)
    rows = _expense_rows(schema, inicio, fim)
    if not rows:
        return AgentResponse(text=f"Não encontrei gastos em {label}.", metadata={"intent": "get_expense_summary", "period": periodo})

    resumo = _summarize_expenses(rows, label)
    _set_financial_context(session, "get_expense_summary", params)
    return AgentResponse(text=resumo, metadata={"intent": "get_expense_summary", "period": periodo})


async def execute_generate_financial_pdf(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})

    params = dict(result.parameters or {})
    periodo = params.get("period")
    if not periodo:
        question = result.clarification_question or "Você quer o relatório de qual período?"
        return _ensure_pending(session, "generate_financial_pdf", params, ["period"], question)

    pdf_info = gerar_pdf_financeiro(schema, periodo=periodo)
    _set_financial_context(session, "generate_financial_pdf", params)
    return AgentResponse(
        text=f"Pronto, gerei o relatório financeiro de {pdf_info['period_label']}.",
        response_type="document",
        document_path=pdf_info["path"],
        document_name=pdf_info["name"],
        metadata={"intent": "generate_financial_pdf", "period": pdf_info["period_label"], "total": pdf_info["total"]},
    )


async def execute_get_financial_chart(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})

    try:
        token_info = gerar_token_acesso(message.user_id)
    except Exception as exc:
        logger.exception("Falha ao gerar token de gráficos: %s", exc)
        return AgentResponse(text="Não consegui abrir os gráficos agora. Tenta novamente em instantes.", metadata={"intent": "get_financial_chart"})
    _set_financial_context(session, "get_financial_chart", dict(result.parameters or {}))
    return AgentResponse(
        text=(
            "📊 Aqui está o seu link com os gráficos financeiros!\n\n"
            f"🔗 https://dashboard-financas.up.railway.app/?phone={message.user_id}&token={token_info['token']}\n"
            f"⚠️ O link é válido até às {token_info['expira_em'].strftime('%H:%M')} por segurança."
        ),
        metadata={"intent": "get_financial_chart", "token": token_info["token"]},
    )


async def execute_register_invoice(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})

    params = dict(result.parameters or {})
    amount = params.get("amount")
    description = params.get("description")
    missing = [field for field in ("amount", "description") if not params.get(field)]
    if missing:
        question = result.clarification_question or ("Qual é o valor da fatura?" if "amount" in missing else "Qual conta ou fatura você quer registrar?")
        return _ensure_pending(session, "register_invoice", params, missing, question)

    conn = conectar_bd()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            INSERT INTO {schema}.fatura_cartao (descricao, valor, categoria, meio_pagamento, parcela, data_inicio, data_fim)
            VALUES (%s, %s, %s, %s, %s, NOW(), CURRENT_DATE)
            """,
            (description, float(amount), params.get("category") or "geral", params.get("payment_method") or "cartao", "1/1"),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    _set_financial_context(session, "register_invoice", params)
    return AgentResponse(text=f"Pronto, registrei a fatura de {_money(amount)}.", metadata={"intent": "register_invoice"})


async def execute_pay_invoice(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})
    pagar_fatura(schema)
    _set_financial_context(session, "pay_invoice", dict(result.parameters or {}))
    return AgentResponse(text="✅ Fatura registrada como paga.", metadata={"intent": "pay_invoice"})


async def execute_list_invoices(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})

    params = dict(result.parameters or {})
    periodo = params.get("period") or "current_month"
    inicio, fim, label = _period_bounds(periodo)
    rows = _invoice_rows(schema, inicio, fim)
    if not rows:
        return AgentResponse(text=f"Não encontrei faturas em {label}.", metadata={"intent": "list_invoices", "period": periodo})

    linhas = [
        f"• {row[0] or 'fatura'} - {_money(row[1])} - {row[2] or 'geral'} - {row[3] or 'cartao'}"
        for row in rows
    ]
    _set_financial_context(session, "list_invoices", params)
    return AgentResponse(text=f"Encontrei {len(rows)} fatura(s) em {label}:\n" + "\n".join(linhas), metadata={"intent": "list_invoices", "period": periodo})


async def execute_create_reminder(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    params = dict(result.parameters or {})
    missing = [field for field in ("text", "date", "time") if not params.get(field)]
    if missing:
        question = result.clarification_question or ("Certo. Para quando você quer esse lembrete?" if "date" in missing else "Qual horário você quer para o lembrete?")
        return _ensure_pending(session, "create_reminder", params, missing, question)

    cron_expr = f"{params['time'].split(':')[1]} {params['time'].split(':')[0]} * * *"
    agendar_lembrete_cron(message.user_id, params["text"], cron_expr)
    _set_financial_context(session, "create_reminder", params)
    session_store.clear_pending_intent(session.channel, session.user_id)
    return AgentResponse(text=f"⏰ Lembrete agendado com sucesso!\nMensagem: \"{params['text']}\"", metadata={"intent": "create_reminder"})


async def execute_list_reminders(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    from backend.services.gastos_service import listar_lembretes

    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})
    lembretes = listar_lembretes(message.user_id, schema)
    if not lembretes:
        return AgentResponse(text="📭 Você ainda não possui lembretes cadastrados.", metadata={"intent": "list_reminders"})
    resposta = "📋 Seus lembretes:\n\n" + "\n".join([f"• {item['id']} - {item['mensagem']}\n⏰ CRON: {item['cron']}" for item in lembretes])
    _set_financial_context(session, "list_reminders", dict(result.parameters or {}))
    return AgentResponse(text=resposta, metadata={"intent": "list_reminders", "count": len(lembretes)})


async def execute_delete_reminder(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    params = dict(result.parameters or {})
    reminder_id = params.get("id")
    if not reminder_id:
        return _ensure_pending(session, "delete_reminder", params, ["id"], "Qual é o ID do lembrete que você quer apagar?")
    from backend.services.gastos_service import apagar_lembrete

    schema = _session_schema(session)
    if not schema:
        return AgentResponse(text="❌ Usuário sem schema vinculado.", metadata={"intent": result.intent})
    sucesso = apagar_lembrete(message.user_id, int(reminder_id), schema)
    _set_financial_context(session, "delete_reminder", params)
    if sucesso:
        return AgentResponse(text="🗑️ Lembrete apagado com sucesso.", metadata={"intent": "delete_reminder"})
    return AgentResponse(text="Não encontrei esse lembrete para apagar.", metadata={"intent": "delete_reminder"})


async def execute_financial_question(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    return await execute_get_expense_summary(message, session, FinancialIntentResult(
        domain="financial",
        intent="get_expense_summary",
        confidence=result.confidence,
        parameters=result.parameters,
        missing_fields=[],
        clarification_question=None,
        should_execute=True,
    ))


async def execute_general_conversation(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    resposta = await gerar_resposta_conversacional(message, session.state)
    resposta.metadata.setdefault("intent", "general_conversation")
    return resposta


FINANCIAL_TOOLS: dict[str, Callable[[IncomingMessage, SessionData, FinancialIntentResult], Awaitable[AgentResponse]]] = {
    "register_expense": execute_register_expense,
    "register_income": execute_register_income,
    "register_salary": execute_register_salary,
    "get_total_expense": execute_get_total_expense,
    "list_expenses": execute_list_expenses,
    "get_expense_summary": execute_get_expense_summary,
    "generate_financial_pdf": execute_generate_financial_pdf,
    "get_financial_chart": execute_get_financial_chart,
    "register_invoice": execute_register_invoice,
    "pay_invoice": execute_pay_invoice,
    "list_invoices": execute_list_invoices,
    "create_reminder": execute_create_reminder,
    "list_reminders": execute_list_reminders,
    "delete_reminder": execute_delete_reminder,
    "financial_question": execute_financial_question,
    "general_conversation": execute_general_conversation,
}


async def executar_intencao_financeira(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> AgentResponse:
    handler = FINANCIAL_TOOLS.get(result.intent, execute_general_conversation)
    session.state["current_domain"] = "financial" if result.domain == "financial" else session.state.get("current_domain")
    session.state["current_intent"] = result.intent
    session.state["last_financial_action"] = result.intent
    session.state["collected_parameters"] = dict(result.parameters or {})
    logger.info(
        "Finance tool=%s params=%s missing=%s pending=%s",
        result.intent,
        result.parameters,
        result.missing_fields,
        session.state.get("pending_intent"),
    )
    return await handler(message, session, result)
