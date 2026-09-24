import logging
import os
import re
from dataclasses import dataclass
from datetime import date

from openai import APIStatusError, OpenAI, OpenAIError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.intent_example import IntentExample
from backend.schemas.natural_intent import (
    NaturalIntentDecision,
    NaturalIntentParameters,
)
from backend.services.natural_period_service import (
    MONTH_NAMES,
    normalize_language,
    resolve_natural_period,
)


logger = logging.getLogger("uvicorn.error")

DEFAULT_AI_MODEL = "openai/gpt-oss-20b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
HIGH_CONFIDENCE_THRESHOLD = 0.85
CLARIFICATION_CONFIDENCE_THRESHOLD = 0.60

INTENT_DESCRIPTIONS = {
    "consultar_maior_gasto": "maior despesa individual em um período",
    "consultar_categoria_maior_gasto": "categoria com maior soma de despesas",
    "consultar_gasto_categoria": "total gasto em uma categoria ou descrição",
    "consultar_ultimas_transacoes": "últimas despesas ou movimentações",
    "consultar_gastos_periodo": "total de despesas em um período",
    "consultar_receitas_periodo": "total de receitas em um período",
    "analisar_financas": "resumo da saúde financeira com cálculos existentes",
    "sugerir_melhorias_financeiras": "orientações baseadas nos Insights existentes",
    "consultar_meta_mais_proxima": "meta ativa com maior progresso",
    "consultar_status_metas": "progresso agregado das metas",
    "extrato_meta": "histórico de aportes de uma meta",
}

PREEMPTIVE_READ_ONLY_INTENTS = {
    "consultar_maior_gasto",
    "consultar_categoria_maior_gasto",
    "consultar_gasto_categoria",
    "consultar_ultimas_transacoes",
    "analisar_financas",
    "sugerir_melhorias_financeiras",
    "consultar_meta_mais_proxima",
    "consultar_status_metas",
    "extrato_meta",
}

EXTENDED_PERIODS = {
    "day_before_yesterday",
    "previous_week",
    "last_7_days",
    "last_15_days",
    "last_30_days",
    "named_month",
    "specific_day",
}


def should_preempt_existing_financial_router(
    decision: NaturalIntentDecision,
) -> bool:
    if decision.intent in PREEMPTIVE_READ_ONLY_INTENTS:
        return True
    return (
        decision.intent
        in {"consultar_gastos_periodo", "consultar_receitas_periodo"}
        and decision.parameters.period in EXTENDED_PERIODS
    )


@dataclass(frozen=True)
class IntentRouteOutcome:
    decision: NaturalIntentDecision | None
    failure_reason: str | None = None


def route_natural_intent(
    db: Session,
    *,
    text: str,
    current_date: date,
    conversation_context: str | None = None,
) -> IntentRouteOutcome:
    deterministic = route_deterministic_intent(text, current_date=current_date)
    if deterministic is not None:
        return IntentRouteOutcome(decision=deterministic)

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return IntentRouteOutcome(decision=None, failure_reason="provider_unavailable")

    examples = _active_examples(db)
    allowed = "\n".join(
        f"- {intent}: {description}"
        for intent, description in INTENT_DESCRIPTIONS.items()
    )
    example_text = "\n".join(
        f'- "{phrase}" => {intent}' for intent, phrase in examples
    )
    context = conversation_context or "Nenhuma clarificação pendente."
    instructions = f"""
Você é somente um classificador de intenções financeiras em português do Brasil.
Não execute ações, não calcule valores, não crie, edite ou exclua dados.
Retorne exclusivamente o schema estruturado solicitado.

Intenções permitidas:
{allowed}
- unknown: nenhuma das intenções acima.

Exemplos supervisionados ativos:
{example_text}

Contexto curto da conversa:
{context}

A data atual é {current_date.isoformat()}.
Identifique períodos semanticamente; o backend calculará as datas.
Use confidence conservadora. Em ambiguidade entre maior despesa individual e
categoria de maior gasto, retorne candidates com as duas opções e uma pergunta
curta. Nunca transforme uma frase em ação de escrita.
""".strip()

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            timeout=15.0,
            max_retries=1,
        )
        response = client.responses.parse(
            model=os.getenv("AI_MODEL", DEFAULT_AI_MODEL),
            instructions=instructions,
            input=f"Mensagem normalizada: {normalize_language(text)}",
            text_format=NaturalIntentDecision,
            temperature=0,
        )
    except APIStatusError as exc:
        logger.error(
            "Erro do roteador Groq: status HTTP=%s; tipo=%s",
            exc.status_code,
            type(exc).__name__,
        )
        return IntentRouteOutcome(decision=None, failure_reason="provider_error")
    except OpenAIError as exc:
        logger.error("Erro do roteador Groq: tipo=%s", type(exc).__name__)
        return IntentRouteOutcome(decision=None, failure_reason="provider_error")
    except Exception as exc:
        logger.error("Resposta inválida do roteador: tipo=%s", type(exc).__name__)
        return IntentRouteOutcome(decision=None, failure_reason="invalid_json")

    if response.output_parsed is None:
        return IntentRouteOutcome(decision=None, failure_reason="invalid_json")
    return IntentRouteOutcome(decision=response.output_parsed)


def route_deterministic_intent(
    text: str,
    *,
    current_date: date,
) -> NaturalIntentDecision | None:
    normalized = normalize_language(text)
    if not normalized:
        return None
    period = resolve_natural_period(text, current_date=current_date)
    period_params = {
        "period": period.key,
        "month": _named_month(normalized),
    }

    transaction_list = _transaction_list_query(normalized)
    if transaction_list is not None:
        limit, transaction_type = transaction_list
        return _decision(
            "consultar_ultimas_transacoes",
            0.98,
            limit=limit,
            transaction_type=transaction_type,
            **period_params,
        )

    if re.search(
        r"\b(maior (?:gasto|despesa)|coisa mais cara|mais cara que paguei)\b",
        normalized,
    ) or "torrei mais dinheiro" in normalized:
        return _decision("consultar_maior_gasto", 0.99, **period_params)

    if re.search(
        r"\bonde (?:q )?(?:(?:eu )?gastei mais|mais (?:eu )?gastei)\b",
        normalized,
    ):
        return _decision(
            "consultar_maior_gasto",
            0.75,
            question=(
                "Você quer saber sua maior despesa individual ou a categoria "
                "em que mais gastou?"
            ),
            candidates=[
                "consultar_maior_gasto",
                "consultar_categoria_maior_gasto",
            ],
            **period_params,
        )

    if re.search(
        r"\b(com o que (?:eu )?mais gastei|qual categoria .*mais gastei|"
        r"onde (?:esta|ta) indo mais dinheiro)\b",
        normalized,
    ):
        return _decision("consultar_categoria_maior_gasto", 0.98, **period_params)

    category = _expense_category_query(normalized)
    if category:
        return _decision(
            "consultar_gasto_categoria",
            0.97,
            category=category,
            **period_params,
        )

    if re.search(
        r"\b(como (?:estao|esta|ta) minhas? financas?|"
        r"como (?:estou|to) financeiramente|"
        r"(?:to|estou) gastando demais|minhas contas estao boas)\b",
        normalized,
    ):
        return _decision("analisar_financas", 0.98, period="current_month")

    if re.search(
        r"\b(o que posso melhorar|onde posso economizar|"
        r"o que (?:eu )?deveria cortar|como posso gastar menos)\b",
        normalized,
    ):
        return _decision("sugerir_melhorias_financeiras", 0.98)

    if re.search(
        r"\b(meta|objetivo).*(mais perto|falta menos|quase concluido)\b",
        normalized,
    ):
        return _decision("consultar_meta_mais_proxima", 0.99)

    if re.search(
        r"\b(como estao minhas metas|quanto falta (?:pras|para as) minhas metas|"
        r"me mostra meu progresso)\b",
        normalized,
    ):
        return _decision("consultar_status_metas", 0.98)

    placed_in_goal = re.search(
        r"\bo que (?:eu )?ja coloquei (?:nessa|nesta|na) meta(?:\s+(.+))?$",
        normalized,
    )
    if placed_in_goal is not None:
        return _decision(
            "extrato_meta",
            0.98,
            goal_name=(placed_in_goal.group(1) or None),
        )

    goal_name = _goal_statement_name(normalized)
    if goal_name:
        return _decision("extrato_meta", 0.98, goal_name=goal_name)

    if period.key == "specific_day" and re.search(
        r"\bmovimentacoes? (?:do|no) dia\b",
        normalized,
    ):
        return _decision(
            "consultar_ultimas_transacoes",
            0.99,
            limit=10,
            **period_params,
        )

    if re.search(
        r"\b(?:quanto|qnt) (?:eu )?(?:gastei|gasto)\b|"
        r"\bo que (?:eu )?gastei\b|"
        r"\bgastos? (?:do|no) dia\b",
        normalized,
    ):
        return _decision("consultar_gastos_periodo", 0.96, **period_params)
    if re.search(
        r"\b(?:quanto|qnt) (?:eu )?(?:recebi|ganhei|entrou)|"
        r"\bquanto entrou\b|"
        r"\b(?:recebi|ganhei) quanto\b",
        normalized,
    ):
        return _decision("consultar_receitas_periodo", 0.96, **period_params)
    return None


def _decision(
    intent: str,
    confidence: float,
    *,
    question: str | None = None,
    candidates: list[str] | None = None,
    **parameters,
) -> NaturalIntentDecision:
    clean_parameters = {
        key: value for key, value in parameters.items() if value is not None
    }
    return NaturalIntentDecision(
        intent=intent,
        confidence=confidence,
        parameters=NaturalIntentParameters(**clean_parameters),
        clarification_question=question,
        candidates=candidates or [],
    )


def _expense_category_query(normalized: str) -> str | None:
    match = re.search(
        r"\b(?:quanto (?:eu )?gastei|quanto foi)\s+(?:com|de|em)\s+(.+)",
        normalized,
    )
    if match is None:
        return None
    category = match.group(1)
    category = re.sub(
        rf"\b\d{{1,2}}\s+de\s+(?:{'|'.join(MONTH_NAMES)})"
        r"(?:\s+de\s+\d{4})?\b.*$",
        "",
        category,
    ).strip()
    category = re.sub(
        r"\b(?:hoje|ontem|anteontem|(?:essa|esta|nesta) semana|"
        r"semana passada|ultima semana|(?:esse|este|neste|deste|desse) mes|"
        r"mes atual|mes passado|mes anterior|nos ultimos \d+ dias)\b.*$",
        "",
        category,
    ).strip()
    for month in MONTH_NAMES:
        category = re.sub(rf"\b(?:em|no mes de|de)\s+{month}\b.*$", "", category).strip()
    if category in MONTH_NAMES or category in {
        "hoje",
        "ontem",
        "anteontem",
        "essa semana",
        "semana passada",
        "esse mes",
        "mes passado",
    }:
        return None
    if re.fullmatch(r"\d{1,2}(?:\s+\d{1,2})(?:\s+\d{4})?", category):
        return None
    return category or None


def _transaction_list_query(normalized: str) -> tuple[int, str | None] | None:
    patterns = (
        r"\bultimos?\s+(?:(\d+)\s+)?(gastos?|despesas?|movimentacoes?)\b",
        r"\b(?:me\s+)?mostra(?:\s+meus?)?\s+(\d+)\s+"
        r"(gastos?|despesas?|movimentacoes?)\b",
        r"\b(?:quais\s+foram\s+)?(?:meus?\s+)?(\d+)\s+"
        r"maiores?\s+(gastos?|despesas?)\b",
        r"\bgastei\s+por\s+ultimo\b",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match is None:
            continue
        groups = match.groups()
        quantity = next(
            (int(value) for value in groups if value is not None and value.isdigit()),
            5,
        )
        noun = next(
            (
                value
                for value in groups
                if value is not None
                and re.fullmatch(r"gastos?|despesas?|movimentacoes?", value)
            ),
            None,
        )
        return max(1, min(quantity, 20)), (
            "expense"
            if noun is not None and re.fullmatch(r"gastos?|despesas?", noun)
            else None
        )
    return None


def _goal_statement_name(normalized: str) -> str | None:
    patterns = (
        r"\bextrato (?:da meta|do objetivo|do)\s+(.+)$",
        r"\bhistorico (?:da meta|do objetivo|da)\s+(.+)$",
        r"\bquais aportes fiz (?:na meta|no objetivo|no)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            candidate = match.group(1).strip()
            if candidate in {
                "mes",
                "mes atual",
                "mes passado",
                "semana",
                "semana passada",
                "ultimos 30 dias",
            } or candidate in MONTH_NAMES:
                return None
            return candidate
    return None


def _named_month(normalized: str) -> int | None:
    return next(
        (month for name, month in MONTH_NAMES.items() if re.search(rf"\b{name}\b", normalized)),
        None,
    )


def _active_examples(db: Session) -> list[tuple[str, str]]:
    rows = list(
        db.scalars(
            select(IntentExample)
            .where(IntentExample.active.is_(True))
            .order_by(IntentExample.intent, IntentExample.id)
            .limit(36)
        )
    )
    return [(row.intent, row.phrase) for row in rows]
