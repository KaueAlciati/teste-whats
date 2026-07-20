from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.text_normalizer import normalize_user_text, remove_accents_for_matching

logger = logging.getLogger(__name__)


class PendingResolution(BaseModel):
    model_config = ConfigDict(extra="ignore")

    matched: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)
    remaining_fields: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    cancel_intent: bool = False


def _session_field(session: Any, key: str, default: Any = None) -> Any:
    if hasattr(session, "state"):
        return session.state.get(key, default)
    if isinstance(session, dict):
        return session.get(key, default)
    return default


def _set_session_field(session: Any, key: str, value: Any) -> None:
    if hasattr(session, "state"):
        session.state[key] = value
    elif isinstance(session, dict):
        session[key] = value


def _merge_parameters(session: Any) -> dict[str, Any]:
    collected = dict(_session_field(session, "pending_parameters") or {})
    collected.update(_session_field(session, "collected_parameters") or {})
    return collected


def _looks_like_cancel(text: str) -> bool:
    normalized = remove_accents_for_matching(normalize_user_text(text))
    tokens = set(normalized.split())
    return bool(tokens & {"cancelar", "cancela", "parar", "stop", "sair", "esquecer", "deixa"})


def _detect_period(text: str) -> str | None:
    normalized = remove_accents_for_matching(normalize_user_text(text))

    current_month_tokens = {
        "esse mes",
        "este mes",
        "desse mes",
        "deste mes",
        "do mes",
        "mes atual",
        "mes deste",
        "agora",
        "esse mês",
        "este mês",
        "desse mês",
        "deste mês",
        "do mês",
        "mês atual",
    }
    previous_month_tokens = {
        "mes passado",
        "ultimo mes",
        "último mês",
        "ultimo mês",
        "mês passado",
        "mes anterior",
        "do mes passado",
        "do mês passado",
    }
    current_year_tokens = {
        "esse ano",
        "este ano",
        "ano atual",
        "desse ano",
        "deste ano",
    }
    today_tokens = {"hoje", "hj", "de hoje"}
    yesterday_tokens = {"ontem"}

    if any(token in normalized for token in previous_month_tokens):
        return "previous_month"
    if any(token in normalized for token in current_month_tokens):
        return "current_month"
    if any(token in normalized for token in current_year_tokens):
        return "current_year"
    if any(token in normalized for token in today_tokens):
        return "today"
    if any(token in normalized for token in yesterday_tokens):
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


def _resolve_pdf_period(session: Any, text: str, normalized_text: str, collected: dict[str, Any]) -> PendingResolution:
    period = _detect_period(text) or _detect_period(normalized_text)
    if period:
        collected["period"] = period
        return PendingResolution(matched=True, parameters=collected, remaining_fields=[])

    simple_tokens = set(remove_accents_for_matching(normalized_text).split())
    normalized_phrase = remove_accents_for_matching(normalized_text)
    if simple_tokens & {"sim", "isso", "esse", "desse", "pode", "beleza", "blz"} or normalized_phrase in {
        "pode ser",
        "pode gerar",
        "gera agora",
        "gera agr",
        "gerar",
    }:
        collected["period"] = "current_month"
        return PendingResolution(matched=True, parameters=collected, remaining_fields=[])
    if simple_tokens & {"nao", "outro"}:
        collected["period"] = "previous_month"
        return PendingResolution(matched=True, parameters=collected, remaining_fields=[])

    question = _session_field(session, "pending_clarification_question") or "Você quer o relatório deste mês ou de outro período?"
    return PendingResolution(matched=False, parameters=collected, remaining_fields=["period"], clarification_question=question)


def _resolve_graphic_quote(text: str, normalized_text: str, collected: dict[str, Any]) -> PendingResolution:
    normalized = remove_accents_for_matching(normalized_text)
    raw = remove_accents_for_matching(text)

    measurement_match = re.search(r"\b(\d{1,4})\s*(?:x|por|by|×)\s*(\d{1,4})\b", normalized)
    if measurement_match:
        collected["measurement"] = f"{measurement_match.group(1)}x{measurement_match.group(2)}"
    elif "measurement" not in collected:
        if re.search(r"\b\d{1,4}\s*[x×]\s*\d{1,4}\b", raw):
            collected["measurement"] = re.search(r"\b\d{1,4}\s*[x×]\s*\d{1,4}\b", raw).group(0).replace(" × ", "x").replace(" ", "")

    quantity_match = re.search(r"\b(\d+)\s*(?:un|unid|unidades|pcs|pçs|pecas|peças)\b", normalized)
    if quantity_match:
        collected["quantity"] = int(quantity_match.group(1))
    elif "quantity" not in collected and re.fullmatch(r"\d+", normalized.strip()):
        collected["quantity"] = int(normalized.strip())

    remaining: list[str] = []
    if "measurement" not in collected:
        remaining.append("measurement")
    if "quantity" not in collected:
        remaining.append("quantity") if "measurement" in collected else None

    if not remaining:
        return PendingResolution(matched=True, parameters=collected, remaining_fields=[])

    if "measurement" in remaining:
        question = "Certo. Qual seria a medida aproximada?"
    else:
        question = "Beleza. Quantas unidades você precisa?"
    return PendingResolution(matched=True, parameters=collected, remaining_fields=remaining, clarification_question=question)


def _resolve_reminder(text: str, normalized_text: str, collected: dict[str, Any]) -> PendingResolution:
    normalized = remove_accents_for_matching(normalized_text)
    if _looks_like_cancel(text):
        return PendingResolution(matched=True, cancel_intent=True, parameters=collected, remaining_fields=[])
    if any(token in normalized for token in {"hoje", "hj"}):
        collected["date"] = "today"
    elif any(token in normalized for token in {"amanha", "amanhã", "depois de amanha", "depois de amanhã"}):
        collected["date"] = "tomorrow"
    elif "ontem" in normalized:
        collected["date"] = "yesterday"

    time_match = re.search(r"\b(\d{1,2})(?:[:h](\d{1,2}))?\b", normalized)
    if time_match and not collected.get("time"):
        hour = time_match.group(1)
        minute = time_match.group(2) or "00"
        collected["time"] = f"{int(hour):02d}:{int(minute):02d}"

    remaining = [field for field in ("text", "date", "time") if not collected.get(field)]
    if not remaining:
        return PendingResolution(matched=True, parameters=collected, remaining_fields=[])
    question = "Certo. Para quando você quer esse lembrete?" if "date" in remaining else "Qual horário você quer para o lembrete?"
    return PendingResolution(matched=True, parameters=collected, remaining_fields=remaining, clarification_question=question)


async def _resolve_with_ai(session: Any, original_text: str, normalized_text: str, collected: dict[str, Any]) -> PendingResolution:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return PendingResolution(matched=False, parameters=collected, remaining_fields=_session_field(session, "pending_missing_fields") or [])

    pending_intent = _session_field(session, "pending_intent")
    missing_fields = _session_field(session, "pending_missing_fields") or []
    last_question = _session_field(session, "pending_clarification_question") or _session_field(session, "last_question")
    history = _session_field(session, "history", [])[-6:]
    summary = "\n".join(f"{item.get('role')}: {item.get('content')}" for item in history if item.get("content"))

    prompt = [
        {
            "role": "system",
            "content": (
                "Você completa uma intenção pendente com base na resposta curta do usuário.\n"
                "Retorne apenas JSON válido com: matched, parameters, remaining_fields, clarification_question, cancel_intent.\n"
                "Não invente campos fora dos já existentes.\n"
                "Se a resposta resolver a pendência, matched deve ser true.\n"
                "Se faltar dado, matched pode ser false e clarification_question deve ser curta.\n"
                "Se o usuário estiver cancelando, use cancel_intent true."
            ),
        },
        {
            "role": "system",
            "content": (
                f"pending_intent={pending_intent}\n"
                f"missing_fields={json.dumps(missing_fields, ensure_ascii=False)}\n"
                f"collected_parameters={json.dumps(collected, ensure_ascii=False)}\n"
                f"last_question={last_question}\n"
                f"contexto_recente:\n{summary or '(vazio)'}"
            ),
        },
        {
            "role": "user",
            "content": f"texto_original={original_text}\ntexto_normalizado={normalized_text}",
        },
    ]

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        completion = await client.chat.completions.create(
            model=os.getenv("OPENAI_INTENT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
            messages=prompt,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        return PendingResolution.model_validate(parsed)
    except Exception as exc:
        logger.exception("Falha ao resolver intenção pendente via IA: %s", exc)
        return PendingResolution(matched=False, parameters=collected, remaining_fields=list(missing_fields))


async def resolve_pending_intent(session: Any, original_text: str, normalized_text: str) -> PendingResolution:
    pending_intent = _session_field(session, "pending_intent")
    if not pending_intent:
        return PendingResolution(matched=False)

    if _looks_like_cancel(original_text):
        return PendingResolution(matched=True, cancel_intent=True, parameters={}, remaining_fields=[])

    collected = _merge_parameters(session)

    if pending_intent == "generate_financial_pdf":
        deterministic = _resolve_pdf_period(session, original_text, normalized_text, collected)
        if deterministic.matched and not deterministic.remaining_fields:
            return deterministic
        ai_resolution = await _resolve_with_ai(session, original_text, normalized_text, collected)
        if ai_resolution.parameters:
            ai_resolution.parameters = {**collected, **ai_resolution.parameters}
        if ai_resolution.matched or ai_resolution.clarification_question or ai_resolution.remaining_fields:
            return ai_resolution
        return deterministic

    if pending_intent == "graphic_quote":
        return _resolve_graphic_quote(original_text, normalized_text, collected)

    if pending_intent == "create_reminder":
        return _resolve_reminder(original_text, normalized_text, collected)

    fallback = PendingResolution(matched=False, parameters=collected, remaining_fields=_session_field(session, "pending_missing_fields") or [])
    if fallback.remaining_fields:
        ai_resolution = await _resolve_with_ai(session, original_text, normalized_text, collected)
        if ai_resolution.parameters:
            ai_resolution.parameters = {**collected, **ai_resolution.parameters}
        return ai_resolution
    return fallback
