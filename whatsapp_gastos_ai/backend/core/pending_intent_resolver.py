from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.financial_agent import FINANCIAL_INTENTS, resolve_pending_financial_message
from backend.core.text_normalizer import extract_period, matching_text, normalize_user_text

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


def _looks_like_cancel(text: str) -> bool:
    normalized = matching_text(text)
    tokens = set(normalized.split())
    return bool(tokens & {"cancelar", "cancela", "parar", "stop", "sair", "esquecer", "deixa"})


def _merge_parameters(session: Any) -> dict[str, Any]:
    collected = dict(_session_field(session, "pending_parameters") or {})
    collected.update(_session_field(session, "collected_parameters") or {})
    return collected


def _resolve_pdf_period(session: Any, original_text: str, normalized_text: str, collected: dict[str, Any]) -> PendingResolution:
    period = extract_period(original_text) or extract_period(normalized_text)
    if period:
        collected["period"] = period
        collected["format"] = collected.get("format") or "pdf"
        return PendingResolution(matched=True, parameters=collected, remaining_fields=[])

    match_text = matching_text(normalized_text)
    simple_tokens = set(match_text.split())
    if simple_tokens & {"sim", "isso", "esse", "desse", "pode", "beleza", "blz"} or match_text in {
        "pode ser",
        "pode gerar",
        "gera agora",
        "gera agr",
        "gerar",
    }:
        collected["period"] = "current_month"
        collected["format"] = collected.get("format") or "pdf"
        return PendingResolution(matched=True, parameters=collected, remaining_fields=[])

    if simple_tokens & {"nao", "outro", "do outro"}:
        collected["period"] = "previous_month"
        collected["format"] = collected.get("format") or "pdf"
        return PendingResolution(matched=True, parameters=collected, remaining_fields=[])

    question = _session_field(session, "pending_clarification_question") or "Voce quer o relatorio deste mes ou de outro periodo?"
    return PendingResolution(matched=False, parameters=collected, remaining_fields=["period"], clarification_question=question)


def _resolve_graphic_quote(original_text: str, normalized_text: str, collected: dict[str, Any]) -> PendingResolution:
    match_text = matching_text(normalized_text)
    measurement_match = re.search(r"\b(\d{1,4})\s*(?:x|por|x|by)\s*(\d{1,4})\b", match_text)
    if measurement_match:
        collected["measurement"] = f"{measurement_match.group(1)}x{measurement_match.group(2)}"

    if not collected.get("quantity"):
        quantity_match = re.search(r"\b(\d+)\s*(?:un|unid|unidades|pecas|pcs)\b", match_text)
        if quantity_match:
            collected["quantity"] = int(quantity_match.group(1))
        elif match_text.isdigit():
            collected["quantity"] = int(match_text)

    remaining: list[str] = []
    if not collected.get("measurement"):
        remaining.append("measurement")
    if collected.get("measurement") and not collected.get("quantity"):
        remaining.append("quantity")

    if not remaining:
        return PendingResolution(matched=True, parameters=collected, remaining_fields=[])

    clarification = "Certo. Qual seria a medida aproximada?" if "measurement" in remaining else "Beleza. Quantas unidades voce precisa?"
    return PendingResolution(matched=True, parameters=collected, remaining_fields=remaining, clarification_question=clarification)


def _resolve_reminder(original_text: str, normalized_text: str, collected: dict[str, Any]) -> PendingResolution:
    match_text = matching_text(normalized_text)
    if _looks_like_cancel(original_text):
        return PendingResolution(matched=True, cancel_intent=True, parameters=collected, remaining_fields=[])

    if "today" in (extract_period(original_text), extract_period(normalized_text), extract_period(match_text)):
        collected["date"] = "today"
    elif "yesterday" in (extract_period(original_text), extract_period(normalized_text), extract_period(match_text)):
        collected["date"] = "yesterday"
    elif "amanha" in match_text:
        collected["date"] = "tomorrow"

    time_match = re.search(r"\b(\d{1,2})(?:[:h](\d{1,2}))?\b", match_text)
    if time_match and not collected.get("time"):
        collected["time"] = f"{int(time_match.group(1)):02d}:{int(time_match.group(2) or '00'):02d}"

    remaining = [field for field in ("text", "date", "time") if not collected.get(field)]
    if not remaining:
        return PendingResolution(matched=True, parameters=collected, remaining_fields=[])

    clarification = "Certo. Para quando voce quer esse lembrete?" if "date" in remaining else "Qual horario voce quer para o lembrete?"
    return PendingResolution(matched=True, parameters=collected, remaining_fields=remaining, clarification_question=clarification)


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
                "Voce completa uma intencao pendente com base na resposta curta do usuario.\n"
                "Retorne apenas JSON valido com: matched, parameters, remaining_fields, clarification_question, cancel_intent.\n"
                "Nao invente campos fora dos ja existentes.\n"
                "Se a resposta resolver a pendencia, matched deve ser true.\n"
                "Se faltar dado, matched pode ser false e clarification_question deve ser curta.\n"
                "Se o usuario estiver cancelando, use cancel_intent true."
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
        {"role": "user", "content": f"texto_original={original_text}\ntexto_normalizado={normalized_text}"},
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
        logger.exception("Falha ao resolver intencao pendente via IA: %s", exc)
        return PendingResolution(matched=False, parameters=collected, remaining_fields=list(missing_fields))


async def resolve_pending_intent(session: Any, original_text: str, normalized_text: str) -> PendingResolution:
    pending_intent = _session_field(session, "pending_intent")
    if not pending_intent:
        return PendingResolution(matched=False)

    if _looks_like_cancel(original_text):
        return PendingResolution(matched=True, cancel_intent=True, parameters={}, remaining_fields=[])

    if pending_intent in FINANCIAL_INTENTS:
        financial_result = resolve_pending_financial_message(session, original_text, normalized_text)
        if financial_result is not None:
            return PendingResolution(
                matched=True,
                parameters=financial_result.parameters,
                remaining_fields=financial_result.missing_fields,
                clarification_question=financial_result.clarification_question,
            )

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
