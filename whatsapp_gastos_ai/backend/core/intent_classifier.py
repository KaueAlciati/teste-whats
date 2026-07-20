from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.core.models import IncomingMessage
from backend.core.text_normalizer import normalize_user_text, remove_accents_for_matching

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


def _session_summary(session_state: dict[str, Any]) -> str:
    history = session_state.get("history", [])[-8:]
    recent = "\n".join(f"{item.get('role')}: {item.get('content')}" for item in history if item.get("content"))
    pending_intent = session_state.get("pending_intent")
    collected = session_state.get("collected_parameters") or {}
    missing = session_state.get("pending_missing_fields") or []
    return (
        f"pending_intent={pending_intent}\n"
        f"collected_parameters={json.dumps(collected, ensure_ascii=False)}\n"
        f"missing_fields={json.dumps(missing, ensure_ascii=False)}\n"
        f"recent_history:\n{recent or '(vazio)'}"
    )


def _normalize(text: str) -> str:
    return normalize_user_text(text)


def _normalize_plain(text: str) -> str:
    return remove_accents_for_matching(_normalize(text))


def _is_greeting(text: str) -> bool:
    normalized = _normalize_plain(text)
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


def _parse_period(text: str) -> str | None:
    normalized = _normalize_plain(text)

    if any(token in normalized for token in {"esse mes", "este mes", "desse mes", "deste mes", "do mes", "mes atual", "agora"}):
        return "current_month"
    if any(token in normalized for token in {"mes passado", "ultimo mes", "ultimo mes", "mes anterior", "do mes passado"}):
        return "previous_month"
    if any(token in normalized for token in {"esse ano", "este ano", "ano atual", "desse ano", "deste ano"}):
        return "current_year"
    if any(token in normalized for token in {"hoje", "de hoje", "hj"}):
        return "today"
    if "ontem" in normalized:
        return "yesterday"
    if re.search(r"\bde\s+[a-zçãõáéíóú]+\s+a\s+[a-zçãõáéíóú]+\b", normalized):
        return "custom_period"
    if re.search(r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b", normalized):
        return "custom_period"
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", normalized):
        return "custom_period"
    if re.search(r"\b(janeiro|fevereiro|marco|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b", normalized):
        return "custom_period"
    return None


def _fallback_pending_intent(text: str, session_state: dict[str, Any]) -> IntentResult | None:
    pending = session_state.get("pending_intent")
    if not pending:
        return None

    normalized = _normalize_plain(text)
    collected = dict(session_state.get("pending_parameters") or session_state.get("collected_parameters") or {})

    if pending == "generate_financial_pdf":
        period = _parse_period(text)
        if period:
            collected["period"] = period
            return IntentResult(
                intent="generate_financial_pdf",
                confidence=0.95,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )

        if normalized in {"sim", "isso", "esse", "desse", "pode", "pode ser", "beleza", "blz"}:
            collected["period"] = "current_month"
            return IntentResult(
                intent="generate_financial_pdf",
                confidence=0.88,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )

        if normalized in {"nao", "não", "outro", "do outro", "mes passado", "mês passado"}:
            collected["period"] = "previous_month"
            return IntentResult(
                intent="generate_financial_pdf",
                confidence=0.88,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )

        return IntentResult(
            intent="generate_financial_pdf",
            confidence=0.62,
            parameters=collected,
            missing_fields=["period"],
            should_execute=False,
            clarification_question="Você quer o relatório deste mês ou de outro período?",
        )

    if pending == "graphic_quote":
        measurement = collected.get("measurement")
        quantity = collected.get("quantity")

        match_measure = re.search(r"\b(\d{1,4})\s*(?:x|por|×)\s*(\d{1,4})\b", normalized)
        if match_measure:
            measurement = f"{match_measure.group(1)}x{match_measure.group(2)}"
            collected["measurement"] = measurement
        elif not measurement and re.fullmatch(r"\d{1,4}\s*[x×]\s*\d{1,4}", normalized.replace(" ", "")):
            normalized_compact = normalized.replace(" ", "")
            piece = re.search(r"\b\d{1,4}\s*[x×]\s*\d{1,4}\b", normalized_compact)
            if piece:
                measurement = piece.group(0).replace("×", "x").replace(" ", "")
                collected["measurement"] = measurement

        match_quantity = re.search(r"\b(\d+)\s*(?:un|unid|unidades|pecas|peças|pcs|pçs)\b", normalized)
        if match_quantity:
            quantity = int(match_quantity.group(1))
            collected["quantity"] = quantity
        elif quantity is None and normalized.isdigit():
            quantity = int(normalized)
            collected["quantity"] = quantity

        remaining = []
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

        clarification = "Certo. Qual seria a medida aproximada?" if "measurement" in remaining else "Beleza. Quantas unidades você precisa?"
        return IntentResult(
            intent="graphic_quote",
            confidence=0.78,
            parameters=collected,
            missing_fields=remaining,
            should_execute=False,
            clarification_question=clarification,
        )

    if pending == "create_reminder":
        if "text" not in collected and text.strip():
            collected["text"] = text.strip()
        if "date" not in collected:
            period = _parse_period(text)
            if period == "today":
                collected["date"] = "today"
            elif period == "yesterday":
                collected["date"] = "yesterday"
            elif period == "current_month":
                collected["date"] = "current_month"
            elif "amanha" in normalized or "amanhã" in normalized:
                collected["date"] = "tomorrow"
        if "time" not in collected:
            match_time = re.search(r"\b(\d{1,2})(?:[:h](\d{1,2}))?\b", normalized)
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

        clarification = "Certo. Para quando você quer esse lembrete?" if "date" in remaining else "Qual horário você quer para o lembrete?"
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
    normalized = _normalize(text)
    normalized_plain = _normalize_plain(text)

    pending_result = _fallback_pending_intent(text, session_state)
    if pending_result:
        return pending_result

    if _is_greeting(text):
        return IntentResult(intent="greeting", confidence=0.95, parameters={}, missing_fields=[], should_execute=True)

    if any(token in normalized_plain for token in {"ajuda", "menu", "comandos"}):
        return IntentResult(intent="help", confidence=0.95, parameters={}, missing_fields=[], should_execute=True)

    amount = _extract_amount(text)
    if amount is not None and any(token in normalized_plain for token in {"gastei", "gasto", "gastos", "paguei", "coloca", "registrar", "anota"}):
        payment_method = None
        if "pix" in normalized_plain:
            payment_method = "pix"
        elif "cartao" in normalized_plain:
            payment_method = "cartao"
        elif "debito" in normalized_plain:
            payment_method = "debito"
        elif "dinheiro" in normalized_plain:
            payment_method = "dinheiro"
        params = {"value": amount, "description": text.strip(), "payment_method": payment_method}
        return IntentResult(
            intent="register_expense",
            confidence=0.93,
            parameters=params,
            missing_fields=[] if payment_method else ["payment_method"],
            should_execute=payment_method is not None,
            clarification_question=None if payment_method is not None else "Foi no pix, cartão, débito ou dinheiro?",
        )

    if any(token in normalized_plain for token in {"pdf", "relatorio", "resumo"}) and any(
        token in normalized_plain for token in {"gasto", "gastos", "conta", "despesa", "despesas"}
    ):
        period = _parse_period(text)
        missing = [] if period else ["period"]
        return IntentResult(
            intent="generate_financial_pdf",
            confidence=0.94,
            parameters={"period": period, "format": "pdf"},
            missing_fields=missing,
            should_execute=period is not None,
            clarification_question=None if period else "Você quer o relatório deste mês ou de outro período?",
        )

    if "quanto" in normalized_plain and "gastei" in normalized_plain:
        period = _parse_period(text) or "current_month"
        return IntentResult(
            intent="get_total_expense",
            confidence=0.92,
            parameters={"period": period},
            missing_fields=[],
            should_execute=True,
        )

    if any(token in normalized_plain for token in {"saldo", "salario", "salário"}):
        return IntentResult(intent="register_salary", confidence=0.83, parameters={"raw_text": text.strip()}, missing_fields=[], should_execute=True)

    if any(token in normalized_plain for token in {"lembra", "lembrete", "recordar"}):
        return IntentResult(
            intent="create_reminder",
            confidence=0.86,
            parameters={"text": text.strip(), "date": None, "time": None},
            missing_fields=["date", "time"],
            should_execute=False,
            clarification_question="Certo. Para quando você quer esse lembrete?",
        )

    if "meus lembretes" in normalized_plain or "listar lembretes" in normalized_plain:
        return IntentResult(intent="list_reminders", confidence=0.9, parameters={}, missing_fields=[], should_execute=True)

    if "apagar lembrete" in normalized_plain or "excluir lembrete" in normalized_plain:
        return IntentResult(
            intent="delete_reminder",
            confidence=0.88,
            parameters={"raw_text": text.strip()},
            missing_fields=["id"],
            should_execute=False,
            clarification_question="Qual é o ID do lembrete que você quer apagar?",
        )

    if any(token in normalized_plain for token in {"dolar", "euro", "cotacao"}):
        currency = None
        if "dolar" in normalized_plain:
            currency = "USD"
        elif "euro" in normalized_plain:
            currency = "EUR"
        return IntentResult(
            intent="get_exchange_rate",
            confidence=0.9,
            parameters={"currency": currency},
            missing_fields=[],
            should_execute=True,
        )

    if re.search(r"\b\d{8}\b", normalized_plain) or "cep" in normalized_plain:
        return IntentResult(intent="lookup_zipcode", confidence=0.9, parameters={"raw_text": text.strip()}, missing_fields=[], should_execute=True)

    if any(token in normalized_plain for token in {"rota", "rotas"}):
        return IntentResult(
            intent="get_route",
            confidence=0.84,
            parameters={"raw_text": text.strip()},
            missing_fields=["destination"],
            should_execute=False,
            clarification_question="Para qual destino você quer calcular a rota?",
        )

    if any(token in normalized_plain for token in {"noticia", "noticias"}):
        return IntentResult(intent="get_news", confidence=0.92, parameters={}, missing_fields=[], should_execute=True)

    if any(token in normalized_plain for token in {"e-mail", "email", "emails"}):
        return IntentResult(intent="get_email_summary", confidence=0.82, parameters={}, missing_fields=[], should_execute=True)

    if any(token in normalized_plain for token in {"grafica", "adesivo", "banner", "placa", "fachada", "impressao", "impressão"}):
        product = None
        for candidate in ("adesivo", "banner", "placa", "fachada", "cartao", "cartão", "panfleto", "flyer"):
            if candidate in normalized:
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

    if any(token in normalized_plain for token in {"voce consegue", "o que voce faz", "oque voce faz"}) or (
        "consegue" in normalized_plain and "fazer" in normalized_plain
    ):
        return IntentResult(intent="general_conversation", confidence=0.72, parameters={}, missing_fields=[], should_execute=True)

    if any(token in normalized_plain for token in {"humano", "atendente", "vendedor", "pessoa"}):
        return IntentResult(intent="human_support", confidence=0.79, parameters={}, missing_fields=[], should_execute=True)

    return IntentResult(
        intent="unknown",
        confidence=0.35,
        parameters={"raw_text": text.strip()},
        missing_fields=[],
        should_execute=False,
        clarification_question="Você quer ajuda com finanças, gráfica, lembretes, cotação ou relatórios?",
    )


async def classify_intent(message: IncomingMessage, session_state: dict[str, Any]) -> IntentResult:
    text = (message.text or "").strip()
    summary = _session_summary(session_state)
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_INTENT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    if not api_key:
        logger.info("Classificador de intenção usando fallback local.")
        return _fallback_classification(message, session_state)

    prompt = [
        {
            "role": "system",
            "content": (
                "Você classifica mensagens de um agente financeiro e de gráfica.\n"
                "Retorne apenas JSON válido com as chaves: intent, confidence, parameters, missing_fields, should_execute, clarification_question.\n"
                f"Use somente uma destas intenções: {', '.join(ALLOWED_INTENTS)}.\n"
                "Não invente intenções fora da lista.\n"
                "Se a mensagem depender da intenção pendente na sessão, complete a intenção atual ao invés de reiniciar o fluxo.\n"
                "Se faltar informação, should_execute deve ser false e clarification_question deve perguntar apenas uma coisa.\n"
                "Se a mensagem for conversa livre, use general_conversation.\n"
                "Se não entender, use unknown e uma pergunta curta e natural.\n"
                "Para orçamento da gráfica, preserve o fluxo em etapas e use graphic_quote.\n"
                "Para relatórios financeiros em PDF, use generate_financial_pdf.\n"
                "Para gastos, use register_expense.\n"
                "Nunca execute operações sensíveis no classificador; apenas identifique intenção e parâmetros."
            ),
        },
        {"role": "system", "content": f"Contexto da sessão:\n{summary}"},
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
        logger.info("Intenção classificada por IA: %s (%.2f)", result.intent, result.confidence)
        return result
    except Exception as exc:
        logger.exception("Erro ao classificar intenção via OpenAI: %s", exc)
        return _fallback_classification(message, session_state)
