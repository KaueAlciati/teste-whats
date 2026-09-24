import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.goal import Goal
from backend.models.user import User
from backend.services.conversation_service import format_brl
from backend.services.goal_context_service import (
    begin_goal_selection,
    clear_pending_goal_selection,
    get_pending_goal_selection,
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

GOAL_LIST_VERBS = {
    "listar",
    "lista",
    "mostra",
    "mostre",
    "mostrar",
    "ver",
    "qual",
    "quais",
}
GOAL_NAME_MATCH_THRESHOLD = 0.72
GOAL_NAME_AMBIGUITY_MARGIN = 0.12
GOAL_NAME_POSSIBLE_MATCH_THRESHOLD = 0.45


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

    if _should_defer_to_natural_router(normalized):
        return False, None

    if _is_goal_list_request(normalized):
        return True, _goals_list_response(
            db,
            user_id=user.id,
            current_time=current_time,
        )

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

    conversational_selection = _conversational_goal_selection(
        db,
        user_id=user.id,
        text=text,
        current_time=current_time,
    )
    if conversational_selection is not None:
        goal, alternatives, selection_was_explicit = conversational_selection
        if goal is None:
            if alternatives:
                names = " ou ".join(f'"{item.name}"' for item in alternatives)
                return True, f"Você quis dizer {names}?"
            if selection_was_explicit:
                return True, "Não encontrei essa meta. Qual delas você quer ver?"
            return False, None
        select_goal_context(
            db,
            user_id=user.id,
            goal=goal,
            current_time=current_time,
        )
        return True, (
            f'✅ Meta "{goal.name}" selecionada.\n'
            f"{_goal_progress_response(goal)}"
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


def _goals_list_response(
    db: Session,
    *,
    user_id: int,
    current_time: datetime,
) -> str:
    goals = list_goals(db, user_id=user_id)
    if not goals:
        clear_pending_goal_selection(db, user_id=user_id)
        return 'Você ainda não tem metas. Envie "criar meta Viagem 3000".'
    displayed_goals = goals[:10]
    begin_goal_selection(
        db,
        user_id=user_id,
        goal_ids=[goal.id for goal in displayed_goals],
        current_time=current_time,
    )
    lines = ["🎯 Suas metas:"]
    for position, goal in enumerate(displayed_goals, start=1):
        status = "concluída" if goal.status == "completed" else f"{_percent(goal):.0f}%"
        lines.append(
            f"{position}. {goal.name}: {format_brl(goal.current_amount)} de "
            f"{format_brl(goal.target_amount)} ({status})"
        )
    lines.append("\nQual delas você quer ver?")
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
    named_target = re.search(r"\b(?:no|na)\s+(.+)$", normalized)
    if named_target is not None:
        requested_name = re.sub(r"^meta\s+", "", named_target.group(1)).strip()
        goal = _find_goal_by_name(db, user_id=user_id, name=requested_name)
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


def _conversational_goal_selection(
    db: Session,
    *,
    user_id: int,
    text: str,
    current_time: datetime,
) -> tuple[Goal | None, list[Goal], bool] | None:
    goal_ids = get_pending_goal_selection(
        db,
        user_id=user_id,
        current_time=current_time,
    )
    if goal_ids is None:
        selected_goal = get_selected_goal(
            db,
            user_id=user_id,
            current_time=current_time,
        )
        if selected_goal is None:
            return None
        goals = list_goals(db, user_id=user_id)
    else:
        goals_by_id = {
            goal.id: goal
            for goal in db.scalars(
                select(Goal).where(
                    Goal.user_id == user_id,
                    Goal.id.in_(goal_ids),
                )
            )
        }
        goals = [
            goals_by_id[goal_id]
            for goal_id in goal_ids
            if goal_id in goals_by_id
        ]

    if not goals:
        clear_pending_goal_selection(db, user_id=user_id)
        return None

    normalized = _normalize(text)
    ordinal_index = _selection_ordinal_index(normalized)
    if ordinal_index is not None:
        return (
            goals[ordinal_index] if ordinal_index < len(goals) else None,
            [],
            True,
        )

    selection_name, selection_was_explicit = _natural_selection_name(normalized)
    goal, alternatives, possible_match = _resolve_goal_name(
        goals,
        selection_name,
    )
    return (
        goal,
        alternatives,
        selection_was_explicit or possible_match,
    )


def _natural_selection_name(normalized: str) -> tuple[str, bool]:
    for prefix in (
        "quero a meta ",
        "quero o meta ",
        "quero a ",
        "quero o ",
        "quero meta ",
        "quero ",
        "a meta ",
        "o meta ",
        "meta ",
        "a ",
        "o ",
    ):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :].strip(), True
    return normalized, False


def _resolve_goal_name(
    goals: list[Goal],
    selection_name: str,
) -> tuple[Goal | None, list[Goal], bool]:
    requested = _normalize(selection_name)
    if not requested:
        return None, [], True

    exact = [goal for goal in goals if _normalize(goal.name) == requested]
    if exact:
        return exact[0], [], True

    partial = [goal for goal in goals if requested in _normalize(goal.name)]
    if len(partial) == 1:
        return partial[0], [], True
    if len(partial) > 1:
        return None, partial[:2], True

    if len(requested) < 3:
        return None, [], False

    ranked = sorted(
        (
            (
                SequenceMatcher(None, requested, _normalize(goal.name)).ratio(),
                goal,
            )
            for goal in goals
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    best_score, best_goal = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    possible_match = best_score >= GOAL_NAME_POSSIBLE_MATCH_THRESHOLD
    if best_score < GOAL_NAME_MATCH_THRESHOLD:
        return None, [best_goal] if possible_match else [], possible_match
    if second_score and best_score - second_score < GOAL_NAME_AMBIGUITY_MARGIN:
        close_goals = [
            goal
            for score, goal in ranked[:2]
            if best_score - score < GOAL_NAME_AMBIGUITY_MARGIN
        ]
        return None, close_goals, True
    return best_goal, [], True


def _is_goal_list_request(normalized: str) -> bool:
    words = set(normalized.split())
    has_goal_word = bool(words & {"meta", "metas"})
    if not has_goal_word:
        return False
    if normalized in {"meta", "metas", "minha meta", "minhas metas"}:
        return True
    return bool(words & GOAL_LIST_VERBS)


def _selection_ordinal_index(normalized: str) -> int | None:
    ordinal_indexes = {
        "primeira": 0,
        "primeiro": 0,
        "segunda": 1,
        "segundo": 1,
        "terceira": 2,
        "terceiro": 2,
        "quarta": 3,
        "quarto": 3,
        "quinta": 4,
        "quinto": 4,
        "sexta": 5,
        "sexto": 5,
        "setima": 6,
        "setimo": 6,
        "oitava": 7,
        "oitavo": 7,
        "nona": 8,
        "nono": 8,
        "decima": 9,
        "decimo": 9,
    }
    candidate = re.sub(r"^(?:quero\s+)?(?:a|o)\s+", "", normalized)
    return ordinal_indexes.get(candidate)


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
    starts_with_contribution_verb = normalized.startswith(
        (
            "adiciona ",
            "adicionar ",
            "adicione ",
            "aporta ",
            "aporte ",
            "guardar ",
            "guardei ",
        )
    )
    standalone_command = normalized in {
        "adicionar",
        "adiciona",
        "aportar",
        "aporte",
    }
    natural_command_with_amount = bool(
        re.match(r"^(?:coloca|colocar)\s+.*\d", normalized)
    )
    return (
        starts_with_contribution_verb
        or standalone_command
        or natural_command_with_amount
    )


def _should_defer_to_natural_router(normalized: str) -> bool:
    return bool(
        re.search(
            r"\b(?:meta|objetivo).*(?:mais perto|falta menos|quase concluido)\b",
            normalized,
        )
        or re.search(
            r"\b(?:como estao minhas metas|quanto falta (?:pras|para as) minhas metas|"
            r"me mostra meu progresso)\b",
            normalized,
        )
        or (
            re.search(r"\b(?:extrato|historico|aportes)\b", normalized)
            and normalized not in {"extrato", "extrato da meta", "historico"}
        )
        or re.search(
            r"\bo que (?:eu )?ja coloquei (?:nessa|nesta|na) meta\b",
            normalized,
        )
    )


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
