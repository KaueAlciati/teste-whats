from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.core.models import IncomingMessage

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
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _is_greeting(text: str) -> bool:
    text = _normalize(text)
    return text in {"oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "eai", "e aí", "iae", "oi tudo bem", "olá tudo bem"}


def _extract_amount(text: str) -> float | None:
    match = re.search(r"(?:r\$|rs)?\s*(\d+(?:[.,]\d{1,2})?)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _fallback_pending_intent(text: str, session_state: dict[str, Any]) -> IntentResult | None:
    pending = session_state.get("pending_intent")
    normalized = _normalize(text)
    collected = dict(session_state.get("collected_parameters") or {})

    if pending == "generate_financial_pdf":
        if any(token in normalized for token in {"desse mês", "deste mês", "esse mês", "este mês", "mês atual", "mes atual"}):
            collected["period"] = "current_month"
            return IntentResult(
                intent="generate_financial_pdf",
                confidence=0.86,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )
        if any(token in normalized for token in {"mês passado", "mes passado", "último mês", "ultimo mês", "last month"}):
            collected["period"] = "last_month"
            return IntentResult(
                intent="generate_financial_pdf",
                confidence=0.83,
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
        if any(ch in normalized for ch in {"x", "×"}) or re.search(r"\b\d+\s*(?:por|x|×)\s*\d+", normalized):
            collected["measurement"] = text.strip()
            if "quantity" not in collected:
                return IntentResult(
                    intent="graphic_quote",
                    confidence=0.79,
                    parameters=collected,
                    missing_fields=["quantity"],
                    should_execute=False,
                    clarification_question="Beleza. Quantas unidades você precisa?",
                )
        if any(token in normalized for token in {"unidade", "unidades", "qtd", "quantidade"}) and _extract_amount(text) is None:
            return IntentResult(
                intent="graphic_quote",
                confidence=0.7,
                parameters=collected,
                missing_fields=["quantity"],
                should_execute=False,
                clarification_question="Quantas unidades você precisa?",
            )
        if "quantity" in collected and "measurement" in collected:
            return IntentResult(
                intent="graphic_quote",
                confidence=0.8,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )

    if pending == "create_reminder":
        collected["text"] = collected.get("text") or text.strip()
        if any(token in normalized for token in {"amanhã", "amanha", "depois de amanhã", "depois de amanha"}):
            collected["date"] = "tomorrow"
        if re.search(r"\b\d{1,2}[:h]\d{0,2}\b", normalized) or re.search(r"\b\d{1,2}\b", normalized):
            collected["time"] = text.strip()
        missing = [field for field in ("text", "date", "time") if not collected.get(field)]
        if not missing:
            return IntentResult(
                intent="create_reminder",
                confidence=0.8,
                parameters=collected,
                missing_fields=[],
                should_execute=True,
            )
        question = "Qual horário você quer para o lembrete?" if "time" in missing else "O que você quer que eu lembre?"
        return IntentResult(
            intent="create_reminder",
            confidence=0.68,
            parameters=collected,
            missing_fields=missing,
            should_execute=False,
            clarification_question=question,
        )

    return None


def _fallback_classification(message: IncomingMessage, session_state: dict[str, Any]) -> IntentResult:
    text = message.text or ""
    normalized = _normalize(text)

    pending_result = _fallback_pending_intent(text, session_state)
    if pending_result:
        return pending_result

    if _is_greeting(text):
        return IntentResult(intent="greeting", confidence=0.93, parameters={}, missing_fields=[], should_execute=True)

    if "ajuda" in normalized or "menu" in normalized or "comandos" in normalized:
        return IntentResult(intent="help", confidence=0.95, parameters={}, missing_fields=[], should_execute=True)

    amount = _extract_amount(text)
    if any(token in normalized for token in {"gastei", "gasto", "gastos", "paguei", "coloca", "registrar", "anota"}) and amount is not None:
        payment_method = None
        if "pix" in normalized:
            payment_method = "pix"
        elif "cartão" in normalized or "cartao" in normalized:
            payment_method = "cartao"
        elif "débito" in normalized or "debito" in normalized:
            payment_method = "debito"
        elif "dinheiro" in normalized:
            payment_method = "dinheiro"
        params = {
            "value": amount,
            "description": text.strip(),
            "payment_method": payment_method,
        }
        missing = [] if payment_method else ["payment_method"]
        return IntentResult(
            intent="register_expense",
            confidence=0.9,
            parameters=params,
            missing_fields=missing,
            should_execute=not missing,
            clarification_question="Foi no pix, cartão, débito ou dinheiro?" if missing else None,
        )

    if any(token in normalized for token in {"pdf", "relatório", "relatorio", "resumo"}) and any(
        token in normalized for token in {"gasto", "gastos", "conta", "despesa", "despesas"}
    ):
        period = "current_month" if any(token in normalized for token in {"esse mês", "desse mês", "este mês", "deste mês", "mes atual", "mês atual"}) else None
        missing = [] if period else ["period"]
        return IntentResult(
            intent="generate_financial_pdf",
            confidence=0.94,
            parameters={"period": period, "format": "pdf"},
            missing_fields=missing,
            should_execute=not missing,
            clarification_question="Você quer o relatório deste mês ou de outro período?" if missing else None,
        )

    if any(token in normalized for token in {"quanto gastei", "quanto eu gastei", "total gasto", "meus gastos", "quanto foi"}):
        return IntentResult(
            intent="get_total_expense",
            confidence=0.92,
            parameters={"period": "current_month"},
            missing_fields=[],
            should_execute=True,
        )

    if any(token in normalized for token in {"saldo", "salário", "salario"}):
        return IntentResult(intent="register_salary", confidence=0.83, parameters={"raw_text": text.strip()}, missing_fields=[], should_execute=True)

    if any(token in normalized for token in {"lembra", "lembrete", "recordar"}):
        return IntentResult(
            intent="create_reminder",
            confidence=0.86,
            parameters={"text": text.strip(), "date": None, "time": None},
            missing_fields=["date", "time"],
            should_execute=False,
            clarification_question="Certo. Para quando você quer esse lembrete?",
        )

    if "meus lembretes" in normalized or "listar lembretes" in normalized:
        return IntentResult(intent="list_reminders", confidence=0.9, parameters={}, missing_fields=[], should_execute=True)

    if "apagar lembrete" in normalized or "excluir lembrete" in normalized:
        return IntentResult(
            intent="delete_reminder",
            confidence=0.88,
            parameters={"raw_text": text.strip()},
            missing_fields=["id"],
            should_execute=False,
            clarification_question="Qual é o ID do lembrete que você quer apagar?",
        )

    if any(token in normalized for token in {"dólar", "dolar", "euro", "cotação", "cotacao"}):
        return IntentResult(
            intent="get_exchange_rate",
            confidence=0.9,
            parameters={"currency": "USD" if "dolar" in normalized else None},
            missing_fields=[],
            should_execute=True,
        )

    if re.search(r"\b\d{8}\b", normalized) or "cep" in normalized:
        return IntentResult(intent="lookup_zipcode", confidence=0.9, parameters={"raw_text": text.strip()}, missing_fields=[], should_execute=True)

    if any(token in normalized for token in {"rota", "rotas"}):
        return IntentResult(intent="get_route", confidence=0.84, parameters={"raw_text": text.strip()}, missing_fields=["destination"], should_execute=False, clarification_question="Para qual destino você quer calcular a rota?")

    if any(token in normalized for token in {"notícia", "noticias", "notícias"}):
        return IntentResult(intent="get_news", confidence=0.92, parameters={}, missing_fields=[], should_execute=True)

    if any(token in normalized for token in {"e-mail", "email", "emails"}):
        return IntentResult(intent="get_email_summary", confidence=0.82, parameters={}, missing_fields=[], should_execute=True)

    if any(token in normalized for token in {"gráfica", "grafica", "adesivo", "banner", "placa", "fachada", "impressão", "impressao"}):
        product = None
        for candidate in ("adesivo", "banner", "placa", "fachada", "cartao", "cartão", "panfleto", "flyer"):
            if candidate in normalized:
                product = candidate
                break
        params = {"product": product or "produto", "measurement": None, "quantity": None}
        return IntentResult(
            intent="graphic_quote",
            confidence=0.88,
            parameters=params,
            missing_fields=["measurement"],
            should_execute=False,
            clarification_question="Certo. Qual seria a medida aproximada?",
        )

    if any(token in normalized for token in {"você consegue", "o que você faz", "o que consegue fazer", "oque voce faz"}):
        return IntentResult(intent="general_conversation", confidence=0.72, parameters={}, missing_fields=[], should_execute=True)

    if any(token in normalized for token in {"humano", "atendente", "vendedor", "pessoa"}):
        return IntentResult(intent="human_support", confidence=0.79, parameters={}, missing_fields=[], should_execute=True)

    return IntentResult(
        intent="unknown",
        confidence=0.35,
        parameters={"raw_text": text.strip()},
        missing_fields=[],
        should_execute=False,
        clarification_question="Você quer ajuda com finanças, gráfico, lembretes, cotação ou relatórios?",
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
