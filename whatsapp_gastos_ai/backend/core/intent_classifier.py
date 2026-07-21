from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.core.models import IncomingMessage
from backend.core.text_normalizer import extract_period, matching_text, normalize_user_text

logger = logging.getLogger(__name__)

IntentName = Literal[
    "greeting",
    "help",
    "register_expense",
    "get_total_expense",
    "generate_financial_pdf",
    "register_salary",
    "list_reminders",
    "create_reminder",
    "delete_reminder",
    "get_exchange_rate",
    "lookup_zipcode",
    "get_route",
    "get_news",
    "get_email_summary",
    "graphic_quote",
    "graphic_product_question",
    "human_support",
    "general_conversation",
    "unknown",
]


class IntentResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intent: IntentName
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    parameters: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    should_execute: bool = False
    clarification_question: str | None = None


ALLOWED_INTENTS: tuple[IntentName, ...] = (
    "greeting",
    "help",
    "register_expense",
    "get_total_expense",
    "generate_financial_pdf",
    "register_salary",
    "list_reminders",
    "create_reminder",
    "delete_reminder",
    "get_exchange_rate",
    "lookup_zipcode",
    "get_route",
    "get_news",
    "get_email_summary",
    "graphic_quote",
    "graphic_product_question",
    "human_support",
    "general_conversation",
    "unknown",
)

REQUIRED_FIELDS: dict[str, list[str]] = {
    "generate_financial_pdf": ["period"],
    "register_expense": ["value"],
    "create_reminder": ["text", "date", "time"],
    "delete_reminder": ["id"],
    "get_route": ["destination"],
}


def _session_summary(session_state: dict[str, Any]) -> str:
    history = session_state.get("history", [])[-8:]
    recent = "\n".join(f"{item.get('role')}: {item.get('content')}" for item in history if item.get("content"))
    return (
        f"pending_intent={session_state.get('pending_intent')}\n"
        f"collected_parameters={json.dumps(session_state.get('collected_parameters') or {}, ensure_ascii=False)}\n"
        f"missing_fields={json.dumps(session_state.get('pending_missing_fields') or [], ensure_ascii=False)}\n"
        f"recent_history:\n{recent or '(vazio)'}"
    )


def _is_greeting(text: str) -> bool:
    normalized = matching_text(text)
    return normalized in {
        "oi",
        "ola",
        "bom dia",
        "boa tarde",
        "boa noite",
        "eai",
        "e ai",
        "iae",
        "oi tudo bem",
        "ola tudo bem",
        "oi tudo certo",
        "ola tudo certo",
    }


def _extract_amount(text: str) -> float | None:
    match = re.search(r"(?:r\$|rs)?\s*(\d+(?:[.,]\d{1,2})?)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _fallback_pending_intent(text: str, session_state: dict[str, Any]) -> IntentResult | None:
    pending = session_state.get("pending_intent")
    if not pending:
        return None

    original = text or ""
    normal = normalize_user_text(original)
    match_text = matching_text(original)
    collected = dict(session_state.get("pending_parameters") or session_state.get("collected_parameters") or {})

    if pending == "generate_financial_pdf":
        period = extract_period(original)
        if period:
            collected["period"] = period
            collected["format"] = collected.get("format") or "pdf"
            return IntentResult(
                intent="generate_financial_pdf",
                confidence=0.98,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )

        if match_text in {"sim", "isso", "esse", "desse", "pode", "pode ser", "beleza", "blz", "pode gerar", "gera agora", "gera agr", "gerar"}:
            collected["period"] = "current_month"
            collected["format"] = collected.get("format") or "pdf"
            return IntentResult(
                intent="generate_financial_pdf",
                confidence=0.9,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )

        if match_text in {"nao", "outro", "do outro"}:
            collected["period"] = "previous_month"
            collected["format"] = collected.get("format") or "pdf"
            return IntentResult(
                intent="generate_financial_pdf",
                confidence=0.9,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )

        return IntentResult(
            intent="generate_financial_pdf",
            confidence=0.6,
            parameters=collected,
            missing_fields=["period"],
            should_execute=False,
            clarification_question="Voce quer o relatorio deste mes ou de outro periodo?",
        )

    if pending == "graphic_quote":
        measurement = collected.get("measurement")
        quantity = collected.get("quantity")
        match_measure = re.search(r"\b(\d{1,4})\s*(?:x|por|×)\s*(\d{1,4})\b", match_text)
        if match_measure:
            measurement = f"{match_measure.group(1)}x{match_measure.group(2)}"
            collected["measurement"] = measurement
        if not quantity:
            match_quantity = re.search(r"\b(\d+)\s*(?:un|unid|unidades|pecas|peças|pcs|pçs)\b", match_text)
            if match_quantity:
                quantity = int(match_quantity.group(1))
                collected["quantity"] = quantity
            elif match_text.isdigit():
                quantity = int(match_text)
                collected["quantity"] = quantity

        remaining: list[str] = []
        if not collected.get("measurement"):
            remaining.append("measurement")
        if collected.get("measurement") and not collected.get("quantity"):
            remaining.append("quantity")

        if not remaining:
            return IntentResult(
                intent="graphic_quote",
                confidence=0.95,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )
        clarification = "Certo. Qual seria a medida aproximada?" if "measurement" in remaining else "Beleza. Quantas unidades voce precisa?"
        return IntentResult(
            intent="graphic_quote",
            confidence=0.78,
            parameters=collected,
            missing_fields=remaining,
            should_execute=False,
            clarification_question=clarification,
        )

    if pending == "create_reminder":
        if "text" not in collected and original.strip():
            collected["text"] = original.strip()
        if "date" not in collected:
            period = extract_period(original)
            if period == "today":
                collected["date"] = "today"
            elif period == "yesterday":
                collected["date"] = "yesterday"
            elif "amanha" in match_text:
                collected["date"] = "tomorrow"
        if "time" not in collected:
            match_time = re.search(r"\b(\d{1,2})(?:[:h](\d{1,2}))?\b", match_text)
            if match_time:
                collected["time"] = f"{int(match_time.group(1)):02d}:{int(match_time.group(2) or '00'):02d}"

        remaining = [field for field in ("text", "date", "time") if not collected.get(field)]
        if not remaining:
            return IntentResult(
                intent="create_reminder",
                confidence=0.9,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )
        clarification = "Certo. Para quando voce quer esse lembrete?" if "date" in remaining else "Qual horario voce quer para o lembrete?"
        return IntentResult(
            intent="create_reminder",
            confidence=0.7,
            parameters=collected,
            missing_fields=remaining,
            should_execute=False,
            clarification_question=clarification,
        )

    return None


def _fallback_classification(message: IncomingMessage, session_state: dict[str, Any]) -> IntentResult:
    text = message.text or ""
    normalized = normalize_user_text(text)
    match_text = matching_text(text)

    pending_result = _fallback_pending_intent(text, session_state)
    if pending_result:
        return pending_result

    if _is_greeting(text):
        return IntentResult(intent="greeting", confidence=0.95, parameters={}, missing_fields=[], should_execute=True)

    if any(token in match_text for token in {"ajuda", "menu", "comandos"}):
        return IntentResult(intent="help", confidence=0.95, parameters={}, missing_fields=[], should_execute=True)

    amount = _extract_amount(text)
    if amount is not None and any(token in match_text for token in {"gastei", "gasto", "gastos", "paguei", "coloca", "registrar", "anota"}):
        payment_method = None
        if "pix" in match_text:
            payment_method = "pix"
        elif "cartao" in match_text:
            payment_method = "cartao"
        elif "debito" in match_text:
            payment_method = "debito"
        elif "dinheiro" in match_text:
            payment_method = "dinheiro"
        params = {"value": amount, "description": text.strip(), "payment_method": payment_method}
        return IntentResult(
            intent="register_expense",
            confidence=0.93,
            parameters=params,
            missing_fields=[] if payment_method else ["payment_method"],
            should_execute=payment_method is not None,
            clarification_question=None if payment_method is not None else "Foi no pix, cartao, debito ou dinheiro?",
        )

    if any(token in match_text for token in {"pdf", "relatorio", "resumo"}) and any(
        token in match_text for token in {"gasto", "gastos", "conta", "despesa", "despesas"}
    ):
        period = extract_period(text)
        params = {"period": period, "format": "pdf"}
        missing = [] if period else ["period"]
        return IntentResult(
            intent="generate_financial_pdf",
            confidence=0.95,
            parameters=params,
            missing_fields=missing,
            should_execute=not missing,
            clarification_question=None if period else "Voce quer o relatorio deste mes ou de outro periodo?",
        )

    if "quanto" in match_text and "gastei" in match_text:
        period = extract_period(text) or "current_month"
        return IntentResult(
            intent="get_total_expense",
            confidence=0.93,
            parameters={"period": period},
            missing_fields=[],
            should_execute=True,
        )

    if any(token in match_text for token in {"saldo", "salario"}):
        return IntentResult(intent="register_salary", confidence=0.83, parameters={"raw_text": text.strip()}, missing_fields=[], should_execute=True)

    if any(token in match_text for token in {"lembra", "lembrete", "recordar"}):
        return IntentResult(
            intent="create_reminder",
            confidence=0.86,
            parameters={"text": text.strip(), "date": None, "time": None},
            missing_fields=["date", "time"],
            should_execute=False,
            clarification_question="Certo. Para quando voce quer esse lembrete?",
        )

    if "meus lembretes" in match_text or "listar lembretes" in match_text:
        return IntentResult(intent="list_reminders", confidence=0.9, parameters={}, missing_fields=[], should_execute=True)

    if "apagar lembrete" in match_text or "excluir lembrete" in match_text:
        return IntentResult(
            intent="delete_reminder",
            confidence=0.88,
            parameters={"raw_text": text.strip()},
            missing_fields=["id"],
            should_execute=False,
            clarification_question="Qual e o ID do lembrete que voce quer apagar?",
        )

    if any(token in match_text for token in {"dolar", "euro", "cotacao"}):
        currency = "USD" if "dolar" in match_text else "EUR" if "euro" in match_text else None
        return IntentResult(
            intent="get_exchange_rate",
            confidence=0.9,
            parameters={"currency": currency},
            missing_fields=[],
            should_execute=True,
        )

    if re.search(r"\b\d{8}\b", match_text) or "cep" in match_text:
        return IntentResult(intent="lookup_zipcode", confidence=0.9, parameters={"raw_text": text.strip()}, missing_fields=[], should_execute=True)

    if any(token in match_text for token in {"rota", "rotas"}):
        return IntentResult(
            intent="get_route",
            confidence=0.84,
            parameters={"raw_text": text.strip()},
            missing_fields=["destination"],
            should_execute=False,
            clarification_question="Para qual destino voce quer calcular a rota?",
        )

    if any(token in match_text for token in {"noticia", "noticias"}):
        return IntentResult(intent="get_news", confidence=0.92, parameters={}, missing_fields=[], should_execute=True)

    if any(token in match_text for token in {"e-mail", "email", "emails"}):
        return IntentResult(intent="get_email_summary", confidence=0.82, parameters={}, missing_fields=[], should_execute=True)

    if any(token in match_text for token in {"grafica", "adesivo", "banner", "placa", "fachada", "impressao"}):
        product = None
        for candidate in ("adesivo", "banner", "placa", "fachada", "cartao", "panfleto", "flyer"):
            if candidate in match_text:
                product = candidate
                break
        return IntentResult(
            intent="graphic_quote",
            confidence=0.88,
            parameters={"product": product or "produto", "measurement": None, "quantity": None},
            missing_fields=["measurement"],
            should_execute=False,
            clarification_question="Certo. Qual seria a medida aproximada?",
        )

    if any(token in match_text for token in {"voce consegue", "o que voce faz", "oque voce faz"}) or (
        "consegue" in match_text and "fazer" in match_text
    ):
        return IntentResult(intent="general_conversation", confidence=0.72, parameters={}, missing_fields=[], should_execute=True)

    if any(token in match_text for token in {"humano", "atendente", "vendedor", "pessoa"}):
        return IntentResult(intent="human_support", confidence=0.79, parameters={}, missing_fields=[], should_execute=True)

    return IntentResult(
        intent="unknown",
        confidence=0.35,
        parameters={"raw_text": text.strip()},
        missing_fields=[],
        should_execute=False,
        clarification_question="Voce quer ajuda com finanças, grafica, lembretes, cotacao ou relatorios?",
    )


def _finalize_result(message: IncomingMessage, session_state: dict[str, Any], result: IntentResult) -> IntentResult:
    text = message.text or ""
    normalized_text = normalize_user_text(text)
    match_text = matching_text(text)

    params = dict(session_state.get("collected_parameters") or {})
    params.update(result.parameters or {})

    if result.intent == "generate_financial_pdf":
        params["format"] = params.get("format") or "pdf"
        period = params.get("period") or extract_period(text) or extract_period(normalized_text) or extract_period(match_text)
        if period:
            params["period"] = period
    elif result.intent == "get_total_expense":
        period = params.get("period") or extract_period(text) or extract_period(normalized_text) or extract_period(match_text) or "current_month"
        params["period"] = period
    elif result.intent == "graphic_quote":
        if not params.get("measurement"):
            match_measure = re.search(r"\b(\d{1,4})\s*(?:x|por|×)\s*(\d{1,4})\b", match_text)
            if match_measure:
                params["measurement"] = f"{match_measure.group(1)}x{match_measure.group(2)}"
        if not params.get("quantity"):
            match_quantity = re.search(r"\b(\d+)\s*(?:un|unid|unidades|pecas|peças|pcs|pçs)\b", match_text)
            if match_quantity:
                params["quantity"] = int(match_quantity.group(1))

    required = REQUIRED_FIELDS.get(result.intent, [])
    missing_fields = [field for field in required if not params.get(field)]

    should_execute = result.should_execute and not missing_fields
    if result.intent in {"generate_financial_pdf", "get_total_expense"} and not missing_fields:
        should_execute = True
    clarification_question = None if not missing_fields else result.clarification_question

    updated = result.model_copy(
        update={
            "parameters": params,
            "missing_fields": missing_fields,
            "should_execute": should_execute,
            "clarification_question": clarification_question,
        }
    )

    logger.info(
        "Intent=%s parameters=%s missing=%s pending=%s",
        updated.intent,
        updated.parameters,
        updated.missing_fields,
        session_state.get("pending_intent"),
    )
    logger.info(
        "Texto normalizado=%r matching=%r periodo=%r",
        normalized_text,
        match_text,
        params.get("period"),
    )
    return updated


async def classify_intent(message: IncomingMessage, session_state: dict[str, Any]) -> IntentResult:
    text = (message.text or "").strip()
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_INTENT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    if not api_key:
        logger.info("Classificador de intencao usando fallback local.")
        return _finalize_result(message, session_state, _fallback_classification(message, session_state))

    prompt = [
        {
            "role": "system",
            "content": (
                "Voce classifica mensagens de um agente financeiro e de grafica.\n"
                "Retorne apenas JSON valido com as chaves: intent, confidence, parameters, missing_fields, should_execute, clarification_question.\n"
                f"Use somente uma destas intenções: {', '.join(ALLOWED_INTENTS)}.\n"
                "Nao invente intenções fora da lista.\n"
                "Se a mensagem depender da intenção pendente na sessao, complete a intenção atual ao inves de reiniciar o fluxo.\n"
                "Se faltar informacao, should_execute deve ser false e clarification_question deve perguntar apenas uma coisa.\n"
                "Se a mensagem for conversa livre, use general_conversation.\n"
                "Se nao entender, use unknown e uma pergunta curta e natural.\n"
                "Para orçamento da grafica, preserve o fluxo em etapas e use graphic_quote.\n"
                "Para relatorios financeiros em PDF, use generate_financial_pdf.\n"
                "Para gastos, use register_expense.\n"
                "Nunca execute operacoes sensiveis no classificador; apenas identifique intenção e parametros."
            ),
        },
        {"role": "system", "content": f"Contexto da sessao:\n{_session_summary(session_state)}"},
        {"role": "user", "content": text},
    ]

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
        parsed = json.loads(raw)
        result = IntentResult.model_validate(parsed)
        logger.info("Intencao classificada por IA: %s (%.2f)", result.intent, result.confidence)
        return _finalize_result(message, session_state, result)
    except Exception as exc:
        logger.exception("Erro ao classificar intenção via OpenAI: %s", exc)
        return _finalize_result(message, session_state, _fallback_classification(message, session_state))

