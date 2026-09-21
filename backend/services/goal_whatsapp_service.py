import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.goal import Goal
from backend.models.user import User
from backend.services.conversation_service import format_brl
from backend.services.goal_context_service import (
    get_selected_goal,
    select_goal_context,
)
from backend.services.goal_contribution_service import (
    add_goal_contribution,
    list_goal_contributions,
)
from backend.services.goal_service import create_goal, list_goals, update_goal


TRANSACTION_TERMS = {
    "gastei",
    "comprei",
    "paguei",
    "recebi",
    "ganhei",
    "vendi",
}


def handle_goal_whatsapp_message(
    db: Session,
    *,
    user: User,
    text: str,
    source: str,
    current_time: datetime,
) -> tuple[bool, str | None]:
    normalized = _normalize(text)
    if not normalized:
        return False, None
    if _is_explicit_financial_transaction(normalized):
        return False, None

    if normalized in {"minhas metas", "listar metas", "lista de metas"}:
        return True, _goals_list_response(db, user_id=user.id)

    if _is_create_goal_command(normalized):
        return True, _create_goal_response(
            db,
            user=user,
            text=text,
            current_time=current_time,
        )

    if _is_add_contribution_command(normalized):
        return True, _add_contribution_response(
            db,
            user=user,
            text=text,
            source=source,
            current_time=current_time,
        )

    if normalized.startswith("quanto falta"):
        goal = _goal_from_command_or_context(
            db,
            user_id=user.id,
            text=text,
            current_time=current_time,
        )
        if goal is None:
            return True, _select_goal_prompt()
        return True, (
            f'Para a meta "{goal.name}", faltam '
            f"{format_brl(_missing(goal))}."
        )

    if normalized.startswith("progresso") or normalized in {
        "como esta minha meta",
        "como esta a meta",
    }:
        goal = _goal_from_command_or_context(
            db,
            user_id=user.id,
            text=text,
            current_time=current_time,
        )
        if goal is None:
            return True, _select_goal_prompt()
        return True, _goal_progress_response(goal)

    if normalized in {"extrato", "extrato da meta", "historico", "histórico"}:
        goal = get_selected_goal(
            db,
            user_id=user.id,
            current_time=current_time,
        )
        if goal is None:
            return True, _select_goal_prompt()
        return True, _goal_history_response(db, user_id=user.id, goal=goal)

    if normalized.startswith("concluir meta") or normalized.startswith(
        "finalizar meta"
    ):
        goal = _goal_from_command_or_context(
            db,
            user_id=user.id,
            text=text,
            current_time=current_time,
        )
        if goal is None:
            return True, _select_goal_prompt()
        if goal.status != "completed":
            missing = _missing(goal)
            if missing > 0:
                goal = add_goal_contribution(
                    db,
                    goal_id=goal.id,
                    user_id=user.id,
                    amount=missing,
                    source=source,
                ).goal
            else:
                goal = update_goal(
                    db,
                    goal=goal,
                    user_id=user.id,
                    changes={"status": "completed"},
                )
        return True, (
            f'✅ Meta "{goal.name}" concluída com '
            f"{format_brl(goal.current_amount)}."
        )

    selection_name = _selection_name(text, normalized)
    if selection_name is not None:
        if not selection_name:
            return True, "Qual meta você quer selecionar?"
        goal = _find_goal_by_name(
            db,
            user_id=user.id,
            name=selection_name,
        )
        if goal is None:
            return True, (
                f'Não encontrei a meta "{selection_name}". '
                'Envie "minhas metas" para ver as opções.'
            )
        select_goal_context(
            db,
            user_id=user.id,
            goal=goal,
            current_time=current_time,
        )
        return True, (
            f'🎯 Meta "{goal.name}" selecionada por 30 minutos. '
            'Você pode dizer "adiciona 100", "quanto falta?", '
            '"progresso" ou "extrato".'
        )

    return False, None


def _create_goal_response(
    db: Session,
    *,
    user: User,
    text: str,
    current_time: datetime,
) -> str:
    remaining = re.sub(
        r"^\s*(?:criar|crie|nova)\s+(?:uma\s+)?meta\s*",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    amount_match = re.search(r"(?:R\$\s*)?(\d[\d.,]*)", remaining)
    if amount_match is None:
        return 'Me diga o nome e o valor. Exemplo: "criar meta Viagem 3000".'

    amount = _parse_amount(amount_match.group(1))
    if amount is None:
        return "Não consegui entender o valor da meta. Pode informar novamente?"

    before_amount = remaining[: amount_match.start()].strip(" :-")
    after_amount = remaining[amount_match.end() :].strip(" :-")
    name = _strip_goal_connectors(before_amount)
    if not name:
        name = _strip_goal_connectors(after_amount)
    if not name:
        return 'Qual é o nome da meta? Exemplo: "criar meta Viagem 3000".'

    goal = create_goal(
        db,
        user_id=user.id,
        name=name[:120],
        target_amount=amount,
        target_date=None,
    )
    select_goal_context(
        db,
        user_id=user.id,
        goal=goal,
        current_time=current_time,
    )
    return (
        f'🎯 Meta "{goal.name}" criada com objetivo de '
        f"{format_brl(goal.target_amount)} e já selecionada."
    )


def _add_contribution_response(
    db: Session,
    *,
    user: User,
    text: str,
    source: str,
    current_time: datetime,
) -> str:
    amount_match = re.search(r"(?:R\$\s*)?(\d[\d.,]*)", text)
    if amount_match is None:
        return "Qual valor você quer adicionar à meta?"
    amount = _parse_amount(amount_match.group(1))
    if amount is None:
        return "Não consegui entender o valor do aporte. Pode informar novamente?"

    goal = _goal_from_command_or_context(
        db,
        user_id=user.id,
        text=text,
        current_time=current_time,
    )
    if goal is None:
        return _select_goal_prompt()
    if goal.status == "completed":
        return f'A meta "{goal.name}" já está concluída.'

    result = add_goal_contribution(
        db,
        goal_id=goal.id,
        user_id=user.id,
        amount=amount,
        source=source,
    )
    completed_suffix = " Meta concluída! ✅" if result.goal.status == "completed" else ""
    return (
        f"Aporte de {format_brl(result.contribution.amount)} registrado na meta "
        f'"{result.goal.name}". Progresso: {result.percent:.0f}%. '
        f"Faltam {format_brl(result.missing)}.{completed_suffix}"
    )


def _goals_list_response(db: Session, *, user_id: int) -> str:
    goals = list_goals(db, user_id=user_id)
    if not goals:
        return 'Você ainda não tem metas. Envie "criar meta Viagem 3000".'
    lines = ["🎯 Suas metas:"]
    for goal in goals[:10]:
        status = "concluída" if goal.status == "completed" else f"{_percent(goal):.0f}%"
        lines.append(
            f"• {goal.name}: {format_brl(goal.current_amount)} de "
            f"{format_brl(goal.target_amount)} ({status})"
        )
    lines.append('\nPara selecionar, envie "meta" e o nome. Ex.: "meta Viagem".')
    return "\n".join(lines)


def _goal_progress_response(goal: Goal) -> str:
    return (
        f'🎯 "{goal.name}": {_percent(goal):.0f}% concluída. '
        f"Você guardou {format_brl(goal.current_amount)} de "
        f"{format_brl(goal.target_amount)}. Faltam {format_brl(_missing(goal))}."
    )


def _goal_history_response(db: Session, *, user_id: int, goal: Goal) -> str:
    contributions = list_goal_contributions(
        db,
        goal_id=goal.id,
        user_id=user_id,
    )
    if not contributions:
        return f'A meta "{goal.name}" ainda não possui aportes.'
    lines = [f'📋 Aportes da meta "{goal.name}":']
    for contribution in contributions[:10]:
        lines.append(
            f"• {contribution.created_at.strftime('%d/%m/%Y')}: "
            f"{format_brl(contribution.amount)} ({_source_label(contribution.source)})"
        )
    return "\n".join(lines)


def _goal_from_command_or_context(
    db: Session,
    *,
    user_id: int,
    text: str,
    current_time: datetime,
) -> Goal | None:
    normalized = _normalize(text)
    marker = " meta "
    padded = f" {normalized} "
    if marker in padded:
        name = padded.split(marker, 1)[1].strip(" ?!.,")
        name = re.sub(r"^(?:a|na|da|para)\s+", "", name)
        if name:
            goal = _find_goal_by_name(db, user_id=user_id, name=name)
            if goal is not None:
                select_goal_context(
                    db,
                    user_id=user_id,
                    goal=goal,
                    current_time=current_time,
                )
                return goal
    return get_selected_goal(
        db,
        user_id=user_id,
        current_time=current_time,
    )


def _find_goal_by_name(
    db: Session,
    *,
    user_id: int,
    name: str,
) -> Goal | None:
    requested = _normalize(name)
    goals = list(db.scalars(select(Goal).where(Goal.user_id == user_id)))
    exact = [goal for goal in goals if _normalize(goal.name) == requested]
    if exact:
        return exact[0]
    partial = [goal for goal in goals if requested in _normalize(goal.name)]
    return partial[0] if len(partial) == 1 else None


def _selection_name(text: str, normalized: str) -> str | None:
    prefixes = ("selecionar meta ", "seleciona meta ", "meta ")
    for prefix in prefixes:
        if normalized.startswith(prefix):
            words_to_remove = len(prefix.split())
            return " ".join(text.strip().split()[words_to_remove:]).strip()
    if normalized in {"selecionar meta", "seleciona meta", "meta"}:
        return ""
    return None


def _is_create_goal_command(normalized: str) -> bool:
    return normalized.startswith(
        (
            "criar meta",
            "criar uma meta",
            "crie meta",
            "crie uma meta",
            "nova meta",
        )
    )


def _is_add_contribution_command(normalized: str) -> bool:
    return normalized.startswith(
        (
            "adiciona ",
            "adicionar ",
            "adicione ",
            "aporta ",
            "aporte ",
            "guardar ",
            "guardei ",
        )
    ) or normalized in {"adicionar", "adiciona", "aportar", "aporte"}


def _is_explicit_financial_transaction(normalized: str) -> bool:
    return any(
        re.search(rf"\b{re.escape(term)}\b", normalized)
        for term in TRANSACTION_TERMS
    )


def _parse_amount(raw: str) -> Decimal | None:
    normalized = raw.strip()
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif normalized.count(".") > 1:
        normalized = normalized.replace(".", "")
    elif "." in normalized and len(normalized.rsplit(".", 1)[1]) == 3:
        normalized = normalized.replace(".", "")
    try:
        value = Decimal(normalized).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return value if value.is_finite() and value > 0 else None


def _strip_goal_connectors(value: str) -> str:
    without_prefix = re.sub(
        r"^(?:de|do|da|para|no valor de)\s+",
        "",
        value.strip(),
        flags=re.IGNORECASE,
    ).strip()
    return re.sub(
        r"\s+(?:de|para|no valor de)$",
        "",
        without_prefix,
        flags=re.IGNORECASE,
    ).strip()


def _percent(goal: Goal) -> Decimal:
    return min(
        Decimal("100"),
        ((goal.current_amount / goal.target_amount) * Decimal("100")).quantize(
            Decimal("0.01")
        ),
    )


def _missing(goal: Goal) -> Decimal:
    return max(Decimal("0.00"), goal.target_amount - goal.current_amount)


def _source_label(source: str) -> str:
    labels = {
        "dashboard": "site",
        "whatsapp_text": "WhatsApp texto",
        "whatsapp_audio": "WhatsApp áudio",
        "whatsapp_image": "WhatsApp imagem",
    }
    return labels.get(source, source)


def _select_goal_prompt() -> str:
    return 'Selecione uma meta primeiro. Exemplo: "meta Viagem".'


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold().strip())
    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in without_accents
        ).split()
    )
