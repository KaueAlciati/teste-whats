import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.models.financial_profile import FinancialProfile
from backend.models.user import User
from backend.schemas.insights import (
    AIInsightsContent,
    AIInsightsState,
    DashboardInsightResponse,
    FinancialSummary,
    FinancialProfileResponse,
    InsightsAnalysisResponse,
)
from backend.services.insights_ai_service import (
    InsightsAIServiceError,
    generate_ai_insights,
)
from backend.services.insights_calculation_service import (
    build_deterministic_alerts,
    build_financial_possibilities,
    calculate_financial_health,
    calculate_financial_summary,
)
from backend.services.market_data_service import get_market_analysis


AI_CACHE_TTL = timedelta(hours=6)


def build_insights_analysis(
    db: Session,
    *,
    user: User,
    profile: FinancialProfile,
    force_refresh: bool = False,
    current_date: date | None = None,
    current_time: datetime | None = None,
) -> InsightsAnalysisResponse:
    now = current_time or datetime.now(timezone.utc)
    summary = calculate_financial_summary(
        db,
        user_id=user.id,
        current_date=current_date,
    )
    alerts = build_deterministic_alerts(summary)
    health = calculate_financial_health(summary, profile)
    possibilities = build_financial_possibilities(profile, summary)
    profile_response = financial_profile_response(profile)
    market = get_market_analysis(
        force_refresh=force_refresh,
        current_time=now,
    )
    ai_payload = {
        "financial_profile": _profile_payload(profile),
        "financial_summary": _ai_financial_summary_payload(summary),
        "category_analysis": {
            "distribution": [
                item.model_dump(mode="json")
                for item in summary.category_distribution
            ],
            "changes": [
                item.model_dump(mode="json") for item in summary.category_changes
            ],
        },
        "monthly_comparison": {
            "previous_month_expenses": summary.previous_month_expenses,
            "expense_change_percentage": summary.expense_change_percentage,
            "recent_expense_trend": summary.recent_expense_trend,
        },
        "goals_summary": {
            "active_goals_count": summary.active_goals_count,
            "total_saved": summary.total_saved_in_goals,
            "total_remaining": summary.total_remaining_in_goals,
            "goals": [item.model_dump(mode="json") for item in summary.goals],
        },
        "deterministic_alerts": [
            item.model_dump(mode="json") for item in alerts
        ],
        "market_data": market.model_dump(mode="json", exclude={"cached"}),
    }
    fingerprint = _payload_fingerprint(ai_payload)
    cached_content = _cached_ai_content(
        profile,
        fingerprint=fingerprint,
        now=now,
        allow_expired=False,
    )
    ai_state: AIInsightsState
    if cached_content is not None and not force_refresh:
        ai_state = AIInsightsState(
            available=True,
            cached=True,
            generated_at=profile.analysis_generated_at,
            message=None,
            content=cached_content,
        )
    else:
        try:
            content = _apply_insight_guardrails(
                generate_ai_insights(ai_payload),
                profile=profile,
                summary=summary,
            )
            profile.analysis_cache = {
                "fingerprint": fingerprint,
                "content": content.model_dump(mode="json"),
            }
            profile.analysis_generated_at = now
            db.commit()
            db.refresh(profile)
            profile_response = financial_profile_response(profile)
            ai_state = AIInsightsState(
                available=True,
                cached=False,
                generated_at=profile.analysis_generated_at,
                message=None,
                content=content,
            )
        except InsightsAIServiceError:
            stale_content = _cached_ai_content(
                profile,
                fingerprint=fingerprint,
                now=now,
                allow_expired=True,
            )
            ai_state = AIInsightsState(
                available=stale_content is not None,
                cached=stale_content is not None,
                generated_at=(
                    profile.analysis_generated_at
                    if stale_content is not None
                    else None
                ),
                message=(
                    "A IA está indisponível agora; exibindo a última análise salva."
                    if stale_content is not None
                    else "Não conseguimos gerar o comentário da IA agora, mas seus dados financeiros continuam disponíveis."
                ),
                content=stale_content,
            )

    return InsightsAnalysisResponse(
        generated_at=now,
        profile=profile_response,
        summary=summary,
        health=health,
        alerts=alerts,
        possibilities=possibilities,
        ai=ai_state,
        market=market,
    )


def build_dashboard_insight(
    db: Session,
    *,
    user_id: int,
    profile: FinancialProfile | None,
    current_date: date | None = None,
) -> DashboardInsightResponse:
    if profile is None or not profile.onboarding_completed:
        return DashboardInsightResponse(
            onboarding_completed=False,
            short_insight=(
                "Complete seu perfil financeiro para receber uma análise personalizada."
            ),
        )
    summary = calculate_financial_summary(
        db,
        user_id=user_id,
        current_date=current_date,
    )
    if summary.transaction_count == 0:
        text = "Registre suas primeiras movimentações para liberar análises reais."
    elif summary.free_amount < 0:
        text = (
            "Neste mês, suas despesas estão R$ "
            f"{abs(summary.free_amount):.2f} acima das entradas registradas."
        )
    elif summary.goals and summary.free_amount > 0:
        text = (
            f"Você tem R$ {summary.free_amount:.2f} livres neste mês. "
            f"A meta {summary.goals[0].name} ainda precisa de "
            f"R$ {summary.goals[0].remaining_amount:.2f}."
        )
    elif summary.top_expense_category:
        text = (
            f"Seu saldo mensal está positivo em R$ {summary.free_amount:.2f}; "
            f"a principal categoria de gasto é {summary.top_expense_category}."
        )
    else:
        text = (
            f"Seu saldo mensal entre entradas e despesas é R$ {summary.free_amount:.2f}."
        )
    return DashboardInsightResponse(
        onboarding_completed=True,
        short_insight=text,
    )


def financial_profile_response(
    profile: FinancialProfile,
) -> FinancialProfileResponse:
    return FinancialProfileResponse(
        id=profile.id,
        main_goal=profile.main_goal,
        investment_horizon=profile.investment_horizon,
        risk_profile=profile.risk_profile,
        liquidity_need=profile.liquidity_need,
        has_debts=profile.has_debts,
        income_type=profile.income_type,
        main_priority=profile.main_priority,
        onboarding_completed=profile.onboarding_completed,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _profile_payload(profile: FinancialProfile) -> dict:
    return {
        "main_goal": profile.main_goal,
        "investment_horizon": profile.investment_horizon,
        "risk_profile": profile.risk_profile,
        "liquidity_need": profile.liquidity_need,
        "has_debts": profile.has_debts,
        "income_type": profile.income_type,
        "main_priority": profile.main_priority,
    }


def _payload_fingerprint(payload: dict) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _cached_ai_content(
    profile: FinancialProfile,
    *,
    fingerprint: str,
    now: datetime,
    allow_expired: bool,
) -> AIInsightsContent | None:
    cache = profile.analysis_cache
    generated_at = profile.analysis_generated_at
    if not isinstance(cache, dict) or generated_at is None:
        return None
    if cache.get("fingerprint") != fingerprint:
        return None
    normalized_generated_at = generated_at
    if normalized_generated_at.tzinfo is None and now.tzinfo is not None:
        normalized_generated_at = normalized_generated_at.replace(
            tzinfo=timezone.utc
        )
    if not allow_expired and now - normalized_generated_at > AI_CACHE_TTL:
        return None
    try:
        return AIInsightsContent.model_validate(cache.get("content"))
    except (TypeError, ValueError):
        return None


def _apply_insight_guardrails(
    content: AIInsightsContent,
    *,
    profile: FinancialProfile,
    summary: FinancialSummary,
) -> AIInsightsContent:
    uncategorized = next(
        (
            item
            for item in summary.category_distribution
            if item.category.casefold() == "sem categoria"
        ),
        None,
    )
    def correct_ratio(text: str) -> str:
        return _correct_expense_ratio_language(text, summary)
    safe_cuts = [
        correct_ratio(suggestion)
        for suggestion in content.cut_suggestions
        if not _suggests_total_cut(suggestion)
    ]
    if uncategorized is not None and uncategorized.amount > 0:
        classification = (
            "Classifique primeiro os gastos em Sem categoria antes de decidir "
            "qual redução é adequada."
        )
        safe_cuts = [classification] + [
            suggestion
            for suggestion in safe_cuts
            if "sem categoria" not in suggestion.casefold()
        ]
    if not safe_cuts and summary.current_month_expenses > 0:
        safe_cuts = [
            "Revise despesas não essenciais e teste uma redução gradual, sem "
            "eliminar integralmente uma categoria."
        ]

    steps: list[str] = []
    if uncategorized is not None and uncategorized.amount > 0:
        steps.append("Classificar as movimentações que estão em Sem categoria.")
    elif summary.transaction_count < 10:
        steps.append("Registrar mais movimentações para melhorar a qualidade da análise.")
    if profile.has_debts:
        steps.append("Organizar o orçamento e priorizar as dívidas mais caras.")
    else:
        steps.append("Revisar o orçamento mensal e definir limites realistas.")
    has_reserve = any(
        "reserva" in goal.name.casefold() and goal.current_amount > 0
        for goal in summary.goals
    )
    if not has_reserve:
        steps.append("Começar uma reserva de emergência com liquidez adequada.")
    if summary.active_goals_count > 0:
        steps.append("Revisar o prazo e o ritmo de aporte das metas ativas.")
    else:
        steps.append("Criar uma meta financeira compatível com o orçamento.")
    if not profile.has_debts and has_reserve:
        steps.append(
            "Só então estudar alternativas de investimento compatíveis com prazo, "
            "liquidez e risco."
        )

    return content.model_copy(
        update={
            "financial_summary": correct_ratio(content.financial_summary),
            "positive_points": [
                correct_ratio(item) for item in content.positive_points
            ],
            "attention_points": [
                correct_ratio(item) for item in content.attention_points
            ],
            "improvements": [
                correct_ratio(item) for item in content.improvements
            ],
            "cut_suggestions": safe_cuts,
            "prioritization": (
                "Priorize nesta ordem: qualidade dos dados, orçamento e dívidas, "
                "reserva de emergência, metas e, por último, investimentos."
            ),
            "goals_analysis": correct_ratio(content.goals_analysis),
            "next_steps": [correct_ratio(item) for item in steps[:5]],
        }
    )


def _suggests_total_cut(text: str) -> bool:
    normalized = text.casefold()
    return any(
        marker in normalized
        for marker in (
            "100%",
            "100 %",
            "eliminar a categoria",
            "elimine a categoria",
            "zerar a categoria",
            "zere a categoria",
            "cortar tudo",
            "corte todo",
            "corte toda",
        )
    )


def _ai_financial_summary_payload(summary: FinancialSummary) -> dict:
    payload = summary.model_dump(mode="json")
    percentage = payload.pop("committed_income_percentage")
    payload["expense_to_income_percentage"] = percentage
    payload["expense_to_income_percentage_definition"] = (
        "Despesas do mês divididas pelas entradas do mês; não representa "
        "aportes ou comprometimento com metas."
    )
    return payload


def _correct_expense_ratio_language(
    text: str,
    summary: FinancialSummary,
) -> str:
    percentage = summary.committed_income_percentage
    if percentage is None:
        return text
    pattern = re.compile(
        r"\b\d+(?:[.,]\d+)?\s*%\s+d(?:a|as|e)\s+"
        r"(?:receitas?|renda|entradas?)\s+"
        r"(?:est[aã]o\s+|s[aã]o\s+)?comprometid[ao]s?\s+"
        r"(?:em|com)\s+metas\b",
        re.IGNORECASE,
    )
    corrected = f"{percentage:.1f}".replace(".", ",")
    return pattern.sub(
        f"{corrected}% da renda comprometida com despesas",
        text,
    )
