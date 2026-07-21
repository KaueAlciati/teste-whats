from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from backend.core.models import IncomingMessage, SessionData
from backend.core.text_normalizer import build_text_variants, extract_period, matching_text, normalize_user_text

logger = logging.getLogger(__name__)

FinancialDomain = Literal["financial", "other"]
FinancialIntentName = Literal[
    "register_expense",
    "register_income",
    "register_salary",
    "get_total_expense",
    "list_expenses",
    "get_expense_summary",
    "generate_financial_pdf",
    "get_financial_chart",
    "register_invoice",
    "pay_invoice",
    "list_invoices",
    "create_reminder",
    "list_reminders",
    "delete_reminder",
    "financial_question",
    "general_conversation",
    "unknown",
]


class FinancialIntentResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    domain: FinancialDomain = "other"
    intent: FinancialIntentName = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    parameters: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    should_execute: bool = False


FINANCIAL_INTENTS: tuple[FinancialIntentName, ...] = get_args(FinancialIntentName)


FINANCIAL_REQUIRED_FIELDS: dict[str, list[str]] = {
    "register_expense": ["amount", "description"],
    "register_income": ["amount"],
    "register_salary": ["amount"],
    "get_total_expense": [],
    "list_expenses": [],
    "get_expense_summary": [],
    "generate_financial_pdf": ["period"],
    "get_financial_chart": [],
    "register_invoice": ["amount", "description"],
    "pay_invoice": [],
    "list_invoices": [],
    "create_reminder": ["text", "date", "time"],
    "list_reminders": [],
    "delete_reminder": ["id"],
    "financial_question": [],
    "general_conversation": [],
    "unknown": [],
}


INTENT_KEYWORDS: dict[FinancialIntentName, tuple[str, ...]] = {
    "generate_financial_pdf": (
        "pdf",
        "relatorio",
        "relatório",
        "resumo financeiro",
        "movimentacoes",
        "movimentações",
        "despesas em pdf",
        "arquivo",
        "arquivo das minhas despesas",
    ),
    "get_total_expense": (
        "quanto gastei",
        "quanto eu gastei",
        "total gasto",
        "meu gasto",
        "meus gastos",
        "quanto saiu",
        "quanto foi embora",
        "quanto deu tudo",
        "qto gastei",
        "qto eu gastei",
    ),
    "register_expense": (
        "gastei",
        "gasto",
        "paguei",
        "coloca",
        "anota",
        "registra",
        "comprei",
        "saiu da conta",
    ),
    "register_income": (
        "entrou",
        "recebi",
        "ganhei",
        "caiu",
        "pix de",
    ),
    "register_salary": (
        "salario",
        "salário",
        "meu salario caiu",
        "meu salário caiu",
    ),
    "list_expenses": (
        "me mostra meus gastos",
        "quais foram minhas despesas",
        "lista o que eu gastei",
        "me mostra as movimentacoes",
        "me mostra as movimentações",
        "quero ver meus lancamentos",
        "quero ver meus lançamentos",
        "o que eu comprei",
    ),
    "get_expense_summary": (
        "como estao minhas finanças",
        "como estão minhas finanças",
        "to gastando muito",
        "estou gastando mais",
        "onde eu mais gastei",
        "qual categoria pesa mais",
        "me explica meus gastos",
        "como foi esse mes",
        "como foi esse mês",
        "o que posso melhorar",
        "gastei mais que mes passado",
        "gastei mais que mês passado",
    ),
    "get_financial_chart": ("grafico", "gráfico", "chart", "dashboard", "graficos", "gráficos"),
    "register_invoice": ("fatura", "boleto", "conta", "invoice"),
    "pay_invoice": ("pagar fatura", "fatura paga", "paguei a fatura", "baixar fatura"),
    "list_invoices": ("listar faturas", "me mostra minhas faturas", "me mostra meus boletos", "quero ver as contas"),
    "create_reminder": ("lembra", "lembrete", "recordar"),
    "list_reminders": ("meus lembretes", "listar lembretes"),
    "delete_reminder": ("apagar lembrete", "excluir lembrete"),
    "financial_question": (
        "financas",
        "finanças",
        "gastos",
        "resumo",
        "movimentacoes",
        "movimentações",
    ),
    "general_conversation": (),
    "unknown": (),
}


PAYMENT_METHODS = {
    "pix": "pix",
    "pixado": "pix",
    "debito": "debit",
    "débito": "debit",
    "cartao de debito": "debit",
    "cartao debito": "debit",
    "cartao": "credit",
    "cartão": "credit",
    "credito": "credit",
    "crédito": "credit",
    "dinheiro": "cash",
    "cash": "cash",
    "transferencia": "transfer",
    "transferência": "transfer",
    "transfer": "transfer",
    "outro": "other",
}


def _session_summary(session: SessionData) -> str:
    history = (session.state.get("history") or [])[-10:]
    recent = "\n".join(f"{item.get('role')}: {item.get('content')}" for item in history if item.get("content"))
    return (
        f"user_id={session.user_id}\n"
        f"channel={session.channel}\n"
        f"pending_intent={session.state.get('pending_intent')}\n"
        f"pending_missing_fields={json.dumps(session.state.get('pending_missing_fields') or [], ensure_ascii=False)}\n"
        f"pending_parameters={json.dumps(session.state.get('pending_parameters') or {}, ensure_ascii=False)}\n"
        f"last_question={session.state.get('last_question')}\n"
        f"last_financial_action={session.state.get('last_financial_action')}\n"
        f"recent_history:\n{recent or '(vazio)'}"
    )


def _score_keywords(text: str) -> tuple[FinancialIntentName, float]:
    scores: dict[str, float] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        if not keywords:
            continue
        best = 0.0
        for keyword in keywords:
            ratio = SequenceMatcher(None, text, keyword).ratio()
            if keyword in text:
                ratio = max(ratio, 1.0)
            best = max(best, ratio)
        scores[intent] = best
    if not scores:
        return "unknown", 0.0
    intent = max(scores, key=scores.get)
    return intent, scores[intent]


def _normalize_payment_method(text: str | None) -> str | None:
    if not text:
        return None
    normalized = matching_text(text)
    for key, value in PAYMENT_METHODS.items():
        if key in normalized:
            return value
    return None


def _extract_amount(text: str) -> float | None:
    match = re.search(r"(?:r\$|rs)?\s*(\d+(?:[.,]\d{1,2})?)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _extract_description(text: str) -> str | None:
    normalized = matching_text(text)
    cleaned = re.sub(r"(?:r\$|rs)?\s*\d+(?:[.,]\d{1,2})?", " ", normalized)
    cleaned = re.sub(r"\b(pix|debito|débito|cartao|cartão|credito|crédito|dinheiro|transferencia|transferência)\b", " ", cleaned)
    cleaned = re.sub(r"\b(gastei|gasto|gastos|paguei|pago|coloca|anota|registra|comprei|entrou|recebi|ganhei|caiu)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _extract_analysis_type(text: str) -> str | None:
    normalized = matching_text(text)
    if any(token in normalized for token in {"onde eu mais gastei", "qual categoria pesa mais", "categoria"}):
        return "top_category"
    if any(token in normalized for token in {"maior gasto", "qual foi meu maior gasto", "quanto foi o maior"}):
        return "largest_expense"
    if any(token in normalized for token in {"comparar", "mes passado", "mês passado", "mais que"}):
        return "comparison"
    return None


def _deterministic_financial_guess(message: IncomingMessage, session: SessionData) -> FinancialIntentResult:
    variants = build_text_variants(message.text or "")
    match_text = variants.matching
    normalized = variants.normalized
    original = variants.original

    period = extract_period(original) or extract_period(normalized) or extract_period(match_text)
    amount = _extract_amount(original)
    payment_method = _normalize_payment_method(original)
    description = _extract_description(original)

    if _is_greeting_like(original):
        return FinancialIntentResult(
            domain="other",
            intent="general_conversation",
            confidence=0.9,
            parameters={},
            missing_fields=[],
            clarification_question=None,
            should_execute=True,
        )

    if any(phrase in match_text for phrase in {"me mostra minhas despesas", "quero ver minhas movimentacoes", "quero ver minhas movimentaÃ§Ãµes"}):
        intent = "list_expenses"
        confidence = 0.95
    else:
        intent = "unknown"
        confidence = 0.2

    for candidate in (
        "generate_financial_pdf",
        "get_total_expense",
        "register_expense",
        "register_income",
        "register_salary",
        "list_expenses",
        "get_expense_summary",
        "get_financial_chart",
        "register_invoice",
        "pay_invoice",
        "list_invoices",
        "create_reminder",
        "list_reminders",
        "delete_reminder",
        "financial_question",
    ):
        score = 0.0
        for phrase in INTENT_KEYWORDS.get(candidate, ()):
            if phrase in match_text:
                score = max(score, 0.95)
            else:
                ratio = SequenceMatcher(None, match_text, phrase).ratio()
                if ratio > score:
                    score = ratio
        if candidate == "generate_financial_pdf" and (period or any(token in match_text for token in {"pdf", "relatorio", "resumo", "movimentacoes", "despesas"})):
            score = max(score, 0.85 if period else 0.74)
        if candidate == "get_total_expense" and "gastei" in match_text:
            score = max(score, 0.9)
        if candidate == "register_expense" and amount is not None and any(token in match_text for token in {"gastei", "gasto", "paguei", "coloca", "anota", "registra", "comprei"}):
            score = max(score, 0.92)
        if candidate == "register_income" and amount is not None and any(token in match_text for token in {"entrou", "recebi", "ganhei", "caiu"}):
            score = max(score, 0.9)
        if candidate == "get_expense_summary" and any(token in match_text for token in {"financas", "gastos", "resumo", "como", "onde", "categoria"}):
            score = max(score, 0.88)
        if score > confidence:
            intent = candidate  # type: ignore[assignment]
            confidence = score

    parameters: dict[str, Any] = {}
    clarification_question: str | None = None
    should_execute = False

    if intent == "generate_financial_pdf":
        parameters["format"] = "pdf"
        if period:
            parameters["period"] = period
            should_execute = True
        else:
            clarification_question = "Você quer o relatório de qual período?"
    elif intent == "get_total_expense":
        parameters["period"] = period or "current_month"
        should_execute = True
    elif intent == "register_expense":
        if amount is not None:
            parameters["amount"] = amount
        if description:
            parameters["description"] = description
        if payment_method:
            parameters["payment_method"] = payment_method
        missing = [field for field in ("amount", "description") if not parameters.get(field)]
        should_execute = not missing
        if missing:
            clarification_question = "Qual foi o valor?" if "amount" in missing else "Com o que foi esse gasto?"
    elif intent == "register_income":
        if amount is not None:
            parameters["amount"] = amount
        description = description or ("salario" if "salario" in match_text or "salário" in match_text else None)
        if description:
            parameters["description"] = description
        should_execute = amount is not None
        if amount is None:
            clarification_question = "Qual foi o valor que entrou?"
    elif intent == "register_salary":
        if amount is not None:
            parameters["amount"] = amount
        should_execute = amount is not None
        if amount is None:
            clarification_question = "Qual foi o valor do salário?"
    elif intent == "list_expenses":
        parameters["period"] = period or "current_month"
        should_execute = True
    elif intent == "get_expense_summary":
        parameters["period"] = period or "current_month"
        parameters["analysis_type"] = _extract_analysis_type(original)
        should_execute = True
    elif intent == "get_financial_chart":
        parameters["period"] = period or "current_month"
        should_execute = True
    elif intent == "register_invoice":
        if amount is not None:
            parameters["amount"] = amount
        if description:
            parameters["description"] = description
        should_execute = amount is not None and bool(description)
        if amount is None:
            clarification_question = "Qual é o valor da fatura?"
        elif not description:
            clarification_question = "Qual conta ou fatura você quer registrar?"
    elif intent == "pay_invoice":
        parameters["period"] = period or "current_month"
        should_execute = True
    elif intent == "list_invoices":
        parameters["period"] = period or "current_month"
        should_execute = True
    elif intent in {"create_reminder", "list_reminders", "delete_reminder"}:
        parameters["text"] = original
        should_execute = intent != "delete_reminder"
    elif intent == "financial_question":
        parameters["period"] = period or "current_month"
        parameters["analysis_type"] = _extract_analysis_type(original) or "summary"
        should_execute = True
    elif intent == "general_conversation":
        should_execute = True

    if intent == "unknown" and confidence < 0.5:
        if session.state.get("last_financial_action"):
            intent = "financial_question"
            parameters["period"] = period or "current_month"
            should_execute = True
            confidence = 0.55
        else:
            intent = "general_conversation" if any(token in match_text for token in {"oi", "tudo bem", "bom dia", "boa tarde"}) else "unknown"

    required_fields = FINANCIAL_REQUIRED_FIELDS.get(intent, [])
    missing_fields = [field for field in required_fields if not parameters.get(field)]
    if intent in {"get_total_expense", "list_expenses", "get_expense_summary", "get_financial_chart", "pay_invoice", "list_invoices", "financial_question"} and "period" in required_fields:
        parameters["period"] = parameters.get("period") or "current_month"
        missing_fields = [field for field in required_fields if not parameters.get(field)]
    if intent == "generate_financial_pdf" and not parameters.get("period"):
        missing_fields = ["period"]
    should_execute = should_execute and not missing_fields
    if missing_fields and not clarification_question:
        if intent == "register_expense" and "amount" in missing_fields:
            clarification_question = "Qual foi o valor?"
        elif intent == "register_expense" and "description" in missing_fields:
            clarification_question = "Com o que foi esse gasto?"
        elif intent == "register_income" and "amount" in missing_fields:
            clarification_question = "Qual foi o valor que entrou?"
        elif intent == "generate_financial_pdf":
            clarification_question = "Você quer o relatório de qual período?"
        else:
            clarification_question = "Pode me passar mais um detalhe?"

    return FinancialIntentResult(
        domain="financial" if intent != "general_conversation" and intent != "unknown" or any(
            token in match_text for token in {"gasto", "gastos", "relatorio", "relatório", "pdf", "conta", "financas", "finanças", "saldo", "recebi", "entrou", "movimentacoes", "movimentações", "fatura", "boleto", "salario", "salário"}
        )
        else "other",
        intent=intent,
        confidence=min(confidence, 0.99),
        parameters=parameters,
        missing_fields=missing_fields,
        clarification_question=clarification_question,
        should_execute=should_execute,
    )


def _merge_ai_result(base: FinancialIntentResult, ai_data: dict[str, Any]) -> FinancialIntentResult:
    try:
        ai_result = FinancialIntentResult.model_validate(ai_data)
    except Exception:
        return base

    params = dict(base.parameters)
    params.update(ai_result.parameters or {})
    merged = base.model_copy(
        update={
            "domain": ai_result.domain or base.domain,
            "intent": ai_result.intent or base.intent,
            "confidence": max(base.confidence, ai_result.confidence),
            "parameters": params,
            "missing_fields": ai_result.missing_fields or base.missing_fields,
            "clarification_question": ai_result.clarification_question or base.clarification_question,
            "should_execute": ai_result.should_execute or base.should_execute,
        }
    )
    return merged


def _finalize_result(message: IncomingMessage, session: SessionData, result: FinancialIntentResult) -> FinancialIntentResult:
    variants = build_text_variants(message.text or "")
    params = dict(session.state.get("collected_parameters") or {})
    params.update(result.parameters or {})

    if result.intent == "generate_financial_pdf":
        params["format"] = params.get("format") or "pdf"
        if not params.get("period"):
            params["period"] = extract_period(variants.original) or extract_period(variants.normalized) or extract_period(variants.matching)
    elif result.intent in {"get_total_expense", "list_expenses", "get_expense_summary", "get_financial_chart", "pay_invoice", "list_invoices", "financial_question"}:
        params["period"] = params.get("period") or extract_period(variants.original) or extract_period(variants.normalized) or extract_period(variants.matching) or "current_month"

    required_fields = FINANCIAL_REQUIRED_FIELDS.get(result.intent, [])
    missing_fields = [field for field in required_fields if not params.get(field)]
    should_execute = result.should_execute and not missing_fields
    if result.intent in {"get_total_expense", "list_expenses", "get_expense_summary", "get_financial_chart", "pay_invoice", "list_invoices", "financial_question"} and not missing_fields:
        should_execute = True

    finalized = result.model_copy(
        update={
            "parameters": params,
            "missing_fields": missing_fields,
            "should_execute": should_execute,
            "clarification_question": None if not missing_fields else result.clarification_question,
        }
    )

    logger.info(
        "Texto original=%r normalizado=%r matching=%r",
        variants.original,
        variants.normalized,
        variants.matching,
    )
    logger.info(
        "Dominio=%s intencao=%s confiança=%.2f parametros=%s faltando=%s pending=%s",
        finalized.domain,
        finalized.intent,
        finalized.confidence,
        finalized.parameters,
        finalized.missing_fields,
        session.state.get("pending_intent"),
    )
    return finalized


def _is_greeting_like(text: str) -> bool:
    normalized = matching_text(text).strip()
    return normalized in {"oi", "ola", "bom dia", "boa tarde", "boa noite", "e ai", "eai", "iae", "tudo bem", "tudo certo"}


def _is_confirmation_like(text: str) -> bool:
    normalized = matching_text(text).strip()
    tokens = set(normalized.split())
    return bool(tokens & {"sim", "isso", "esse", "desse", "pode", "beleza", "blz", "ok", "gerar", "gera", "manda"})


def _is_negative_like(text: str) -> bool:
    normalized = matching_text(text).strip()
    tokens = set(normalized.split())
    return bool(tokens & {"nao", "outro", "anterior"}) or "do outro" in normalized or "mes passado" in normalized


def resolve_pending_financial_message(session: SessionData, original_text: str, normalized_text: str) -> FinancialIntentResult | None:
    pending_intent = session.state.get("pending_intent")
    if pending_intent not in FINANCIAL_INTENTS:
        return None

    variants = build_text_variants(original_text)
    match_text = variants.matching
    collected = dict(session.state.get("pending_parameters") or session.state.get("collected_parameters") or {})
    intent = str(pending_intent)

    if intent == "generate_financial_pdf":
        period = collected.get("period") or extract_period(original_text) or extract_period(normalized_text) or extract_period(match_text)
        if period:
            collected["period"] = period
            collected["format"] = collected.get("format") or "pdf"
            return FinancialIntentResult(
                domain="financial",
                intent="generate_financial_pdf",
                confidence=0.99,
                parameters=collected,
                missing_fields=[],
                clarification_question=None,
                should_execute=True,
            )
        if _is_confirmation_like(original_text):
            collected["period"] = "current_month"
            collected["format"] = collected.get("format") or "pdf"
            return FinancialIntentResult(
                domain="financial",
                intent="generate_financial_pdf",
                confidence=0.92,
                parameters=collected,
                missing_fields=[],
                clarification_question=None,
                should_execute=True,
            )
        if _is_negative_like(original_text):
            collected["period"] = "previous_month"
            collected["format"] = collected.get("format") or "pdf"
            return FinancialIntentResult(
                domain="financial",
                intent="generate_financial_pdf",
                confidence=0.9,
                parameters=collected,
                missing_fields=[],
                clarification_question=None,
                should_execute=True,
            )
        return FinancialIntentResult(
            domain="financial",
            intent="generate_financial_pdf",
            confidence=0.72,
            parameters=collected,
            missing_fields=["period"],
            clarification_question="Você quer o relatório deste mês ou de outro período?",
            should_execute=False,
        )

    if intent in {"get_total_expense", "list_expenses", "get_expense_summary", "get_financial_chart", "pay_invoice", "list_invoices", "financial_question"}:
        period = collected.get("period") or extract_period(original_text) or extract_period(normalized_text) or extract_period(match_text) or "current_month"
        collected["period"] = period
        analysis_type = collected.get("analysis_type") or _extract_analysis_type(original_text)
        if analysis_type:
            collected["analysis_type"] = analysis_type
        return FinancialIntentResult(
            domain="financial",
            intent=intent,  # type: ignore[arg-type]
            confidence=0.92,
            parameters=collected,
            missing_fields=[],
            clarification_question=None,
            should_execute=True,
        )

    if intent == "register_expense":
        amount = collected.get("amount") or _extract_amount(original_text)
        if amount is not None:
            collected["amount"] = amount
        description = collected.get("description") or _extract_description(original_text)
        if description:
            collected["description"] = description
        payment_method = collected.get("payment_method") or _normalize_payment_method(original_text)
        if payment_method:
            collected["payment_method"] = payment_method
        missing = [field for field in ("amount", "description") if not collected.get(field)]
        return FinancialIntentResult(
            domain="financial",
            intent="register_expense",
            confidence=0.95 if not missing else 0.84,
            parameters=collected,
            missing_fields=missing,
            clarification_question=None if not missing else ("Qual foi o valor?" if "amount" in missing else "Com o que foi esse gasto?"),
            should_execute=not missing,
        )

    if intent == "register_income":
        amount = collected.get("amount") or _extract_amount(original_text)
        if amount is not None:
            collected["amount"] = amount
        description = collected.get("description") or _extract_description(original_text)
        if description:
            collected["description"] = description
        missing = [field for field in ("amount",) if not collected.get(field)]
        return FinancialIntentResult(
            domain="financial",
            intent="register_income",
            confidence=0.92 if not missing else 0.8,
            parameters=collected,
            missing_fields=missing,
            clarification_question=None if not missing else "Qual foi o valor que entrou?",
            should_execute=not missing,
        )

    if intent == "register_salary":
        amount = collected.get("amount") or _extract_amount(original_text)
        if amount is not None:
            collected["amount"] = amount
        missing = [field for field in ("amount",) if not collected.get(field)]
        return FinancialIntentResult(
            domain="financial",
            intent="register_salary",
            confidence=0.92 if not missing else 0.8,
            parameters=collected,
            missing_fields=missing,
            clarification_question=None if not missing else "Qual foi o valor do salário?",
            should_execute=not missing,
        )

    if intent == "register_invoice":
        amount = collected.get("amount") or _extract_amount(original_text)
        if amount is not None:
            collected["amount"] = amount
        description = collected.get("description") or _extract_description(original_text)
        if description:
            collected["description"] = description
        missing = [field for field in ("amount", "description") if not collected.get(field)]
        return FinancialIntentResult(
            domain="financial",
            intent="register_invoice",
            confidence=0.9 if not missing else 0.75,
            parameters=collected,
            missing_fields=missing,
            clarification_question=None if not missing else ("Qual é o valor da fatura?" if "amount" in missing else "Qual conta ou fatura você quer registrar?"),
            should_execute=not missing,
        )

    if intent == "create_reminder":
        if original_text.strip():
            collected.setdefault("text", original_text.strip())
        if not collected.get("date"):
            period = extract_period(original_text) or extract_period(normalized_text) or extract_period(match_text)
            if period == "today":
                collected["date"] = "today"
            elif period == "yesterday":
                collected["date"] = "yesterday"
            elif "amanha" in match_text:
                collected["date"] = "tomorrow"
        if not collected.get("time"):
            time_match = re.search(r"\b(\d{1,2})(?:[:h](\d{1,2}))?\b", match_text)
            if time_match:
                collected["time"] = f"{int(time_match.group(1)):02d}:{int(time_match.group(2) or '00'):02d}"
        missing = [field for field in ("text", "date", "time") if not collected.get(field)]
        return FinancialIntentResult(
            domain="financial",
            intent="create_reminder",
            confidence=0.85 if not missing else 0.72,
            parameters=collected,
            missing_fields=missing,
            clarification_question=None if not missing else ("Certo. Para quando você quer esse lembrete?" if "date" in missing else "Qual horário você quer para o lembrete?"),
            should_execute=not missing,
        )

    if intent in {"list_reminders", "delete_reminder"}:
        return FinancialIntentResult(
            domain="financial",
            intent=intent,  # type: ignore[arg-type]
            confidence=0.9,
            parameters=collected,
            missing_fields=[],
            clarification_question=None,
            should_execute=True,
        )

    return None


async def interpret_financial_message(message: IncomingMessage, session: SessionData) -> FinancialIntentResult:
    pending_resolution = resolve_pending_financial_message(session, message.text or "", build_text_variants(message.text or "").normalized)
    if pending_resolution is not None:
        return _finalize_result(message, session, pending_resolution)

    base = _deterministic_financial_guess(message, session)
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_FINANCIAL_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    summary = _session_summary(session)

    prompt = [
        {
            "role": "system",
            "content": (
                "Você é um classificador financeiro estruturado.\n"
                "Retorne apenas JSON com: domain, intent, confidence, parameters, missing_fields, clarification_question, should_execute.\n"
                f"Use somente uma destas intenções: {', '.join(FINANCIAL_INTENTS)}.\n"
                "Não invente intenções fora da lista.\n"
                "Use os parâmetros padronizados e mantenha period no formato current_month, previous_month, current_week, previous_week, current_year, today, yesterday ou custom_range.\n"
                "Converta meios de pagamento para pix, debit, credit, cash, transfer ou other.\n"
                "Se faltar dado, pergunte apenas uma coisa.\n"
                "Se a intenção estiver completa, should_execute deve ser true."
            ),
        },
        {"role": "system", "content": f"Contexto da sessão:\n{summary}"},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "original_text": message.text or "",
                    "normalized_text": build_text_variants(message.text or "").normalized,
                    "matching_text": build_text_variants(message.text or "").matching,
                    "user_id": message.user_id,
                    "channel": message.channel,
                    "now": datetime.now().isoformat(),
                    "pending_intent": session.state.get("pending_intent"),
                    "last_question": session.state.get("last_question"),
                    "current_domain": session.state.get("current_domain"),
                },
                ensure_ascii=False,
            ),
        },
    ]

    if not api_key:
        return _finalize_result(message, session, base)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        completion = await client.chat.completions.create(
            model=model,
            messages=prompt,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or "{}"
        merged = _merge_ai_result(base, json.loads(raw))
        return _finalize_result(message, session, merged)
    except Exception as exc:
        logger.exception("Falha ao interpretar mensagem financeira via OpenAI: %s", exc)
        return _finalize_result(message, session, base)
