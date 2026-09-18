import unicodedata
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from backend.schemas.financial_intent import FinancialAction, FinancialPeriod


TransactionType = Literal["expense", "income"]

_CATEGORY_EMOJIS = {
    "alimentacao": "🍽️",
    "transporte": "🚗",
    "moradia": "🏠",
    "saude": "🩺",
    "educacao": "📚",
    "lazer": "🎮",
    "compras": "🛍️",
    "assinaturas": "🧾",
    "contas": "🧾",
    "impostos": "🧾",
    "salario": "💼",
    "freelance": "💻",
    "venda": "💵",
    "investimentos": "📈",
    "reembolso": "💵",
    "outros": "💰",
}

_PERIOD_SUFFIXES: dict[FinancialPeriod, str] = {
    "today": "hoje",
    "yesterday": "ontem",
    "current_week": "nesta semana",
    "current_month": "neste mês",
    "previous_month": "no mês passado",
    "all": "no total",
}

_PERIOD_OPENINGS: dict[FinancialPeriod, str] = {
    "today": "Hoje",
    "yesterday": "Ontem",
    "current_week": "Nesta semana",
    "current_month": "Neste mês",
    "previous_month": "No mês passado",
    "all": "No total",
}


def response_variant(seed: str, total: int = 3) -> int:
    if total <= 0:
        raise ValueError("total deve ser maior que zero")
    return sum(seed.encode("utf-8")) % total if seed else 0


def format_brl(value: Decimal) -> str:
    if not isinstance(value, Decimal):
        raise TypeError("value deve ser Decimal")

    formatted = f"{value.quantize(Decimal('0.01')):,.2f}"
    formatted = formatted.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


def format_natural_date(value: date, current_date: date) -> str:
    if value == current_date:
        return "Hoje"
    if value == current_date - timedelta(days=1):
        return "Ontem"
    return value.strftime("%d/%m/%Y")


def transaction_confirmation(
    *,
    transaction_type: TransactionType,
    amount: Decimal,
    description: str,
    category: str,
    transaction_date: date,
    current_date: date,
    user_name: str | None = None,
    variant: int = 0,
) -> str:
    normalized_variant = variant % 3
    name = _first_name(user_name)

    if transaction_type == "expense":
        introductions = (
            "Beleza, já registrei pra você 👌",
            "Pronto! Deixei esse gasto salvo.",
            (
                f"Pronto, {name}. Já registrei esse gasto."
                if name
                else "Anotado! Esse gasto já ficou registrado."
            ),
        )
    else:
        introductions = (
            "Boa! Já registrei essa entrada 👌",
            "Pronto, essa receita já ficou salva.",
            (
                f"Tudo certo, {name}. Já registrei essa entrada."
                if name
                else "Anotado! Essa entrada já ficou registrada."
            ),
        )

    emoji = _transaction_emoji(category, description)
    display_description = _display_text(description)
    return (
        f"{introductions[normalized_variant]}\n\n"
        f"{emoji} {display_description} — {format_brl(amount)}\n"
        f"📂 {category}\n"
        f"📅 {format_natural_date(transaction_date, current_date)}"
    )


def balance_response(
    balance: Decimal,
    *,
    user_name: str | None = None,
    variant: int = 0,
) -> str:
    amount = format_brl(balance)
    name = _first_name(user_name)
    responses = (
        f"Hoje seu saldo está em {amount} 💰",
        f"Você está com {amount} de saldo no momento.",
        f"{name}, seu saldo está em {amount} agora." if name else f"Seu saldo está em {amount} agora.",
    )
    return responses[variant % len(responses)]


def no_transactions_response(
    *,
    user_name: str | None = None,
    variant: int = 0,
) -> str:
    name = _first_name(user_name)
    responses = (
        "Você ainda não tem movimentações registradas.",
        "Ainda não encontrei nenhuma movimentação no seu controle.",
        (
            f"{name}, você ainda não tem movimentações registradas."
            if name
            else "Seu controle ainda não tem movimentações."
        ),
    )
    return responses[variant % len(responses)]


def total_response(
    *,
    transaction_type: TransactionType,
    total: Decimal,
    period: FinancialPeriod,
    user_name: str | None = None,
    variant: int = 0,
) -> str:
    suffix = _PERIOD_SUFFIXES[period]
    opening = _PERIOD_OPENINGS[period]
    normalized_variant = variant % 3
    name = _first_name(user_name)

    if total == Decimal("0"):
        if transaction_type == "expense":
            responses = (
                f"Você não teve gastos {suffix}.",
                f"Não encontrei gastos {suffix}.",
                (
                    f"{name}, não há gastos registrados {suffix}."
                    if name
                    else f"Não há gastos registrados {suffix}."
                ),
            )
        else:
            responses = (
                f"Você não recebeu receitas {suffix}.",
                f"Não encontrei entradas {suffix}.",
                (
                    f"{name}, não há receitas registradas {suffix}."
                    if name
                    else f"Não há receitas registradas {suffix}."
                ),
            )
        return responses[normalized_variant]

    amount = format_brl(total)
    if transaction_type == "expense":
        responses = (
            f"Até agora você gastou {amount} {suffix}.",
            f"Seus gastos somam {amount} {suffix}.",
            (
                f"{name}, seus gastos estão em {amount} {suffix}."
                if name
                else f"Você gastou {amount} {suffix}."
            ),
        )
    else:
        responses = (
            f"{opening} entraram {amount}.",
            f"Você recebeu {amount} {suffix}.",
            (
                f"{name}, suas entradas somam {amount} {suffix}."
                if name
                else f"Suas entradas somam {amount} {suffix}."
            ),
        )
    return responses[normalized_variant]


def clarification_response(
    *,
    action: FinancialAction,
    question: str | None,
    missing_amount: bool,
    missing_description: bool,
) -> str:
    normalized_question = " ".join((question or "").split())
    if normalized_question and not _looks_technical(normalized_question):
        return _ensure_question_mark(normalized_question)

    if missing_amount and action == "create_expense":
        return "Beleza. Quanto você gastou?"
    if missing_amount and action == "create_income":
        return "Quanto você recebeu?"
    if missing_description:
        return "Com o que foi essa movimentação?"
    return "Pode me contar um pouco mais para eu organizar isso?"


def non_financial_response(
    text: str,
    *,
    user_name: str | None = None,
    variant: int = 0,
) -> str:
    normalized_text = _normalize_text(text)
    name = _first_name(user_name)
    name_suffix = f", {name}" if name and variant % 3 == 2 else ""

    if normalized_text.startswith("bom dia"):
        return f"Bom dia{name_suffix}! ☀️ Me conta, como posso te ajudar com suas finanças?"
    if normalized_text.startswith("boa tarde"):
        return f"Boa tarde{name_suffix}! Como posso te ajudar a organizar suas finanças?"
    if normalized_text.startswith("boa noite"):
        return f"Boa noite{name_suffix}! O que você quer organizar hoje?"
    if _is_greeting(normalized_text):
        greetings = (
            "Oi! 👋 Tudo certo? O que você quer organizar hoje?",
            "Olá! Me conta, como posso te ajudar com suas finanças?",
            (
                f"Oi, {name}! 👋 O que vamos organizar hoje?"
                if name
                else "Oi! 👋 Como posso te ajudar hoje?"
            ),
        )
        return greetings[variant % len(greetings)]

    responses = (
        "Meu foco é te ajudar a organizar gastos, receitas e saldo. O que você quer conferir?",
        "Posso cuidar com você dos seus gastos, receitas e saldo. Me conta o que precisa.",
        (
            f"{name}, consigo te ajudar com sua organização financeira."
            if name
            else "Consigo te ajudar com sua organização financeira."
        ),
    )
    return responses[variant % len(responses)]


def ai_error_response() -> str:
    return "Não consegui entender isso agora. Tenta novamente em alguns instantes."


def operation_error_response() -> str:
    return "Não consegui concluir isso agora. Tenta novamente em alguns instantes."


def audio_processing_response(variant: int = 0) -> str:
    responses = (
        "Beleza, vou ouvir isso pra você 🎧",
        "Um instante, vou analisar esse áudio.",
        "Certo, já vou ouvir seu áudio 🎧",
    )
    return responses[variant % len(responses)]


def audio_empty_response() -> str:
    return "Não consegui entender bem esse áudio. Pode mandar de novo?"


def audio_too_large_response() -> str:
    return "Esse áudio ficou grande demais. Pode enviar uma versão menor?"


def audio_error_response() -> str:
    return "Não consegui processar esse áudio agora. Tenta novamente em alguns instantes."


def _transaction_emoji(category: str, description: str) -> str:
    normalized_description = _normalize_text(description)
    if any(
        term in normalized_description
        for term in ("gasolina", "combustivel", "posto")
    ):
        return "⛽"
    return _CATEGORY_EMOJIS.get(_normalize_text(category), "💰")


def _first_name(user_name: str | None) -> str | None:
    normalized_name = " ".join((user_name or "").split())
    return normalized_name.split(" ", 1)[0] if normalized_name else None


def _display_text(value: str) -> str:
    normalized = " ".join(value.split())
    return normalized[:1].upper() + normalized[1:]


def _normalize_text(value: str) -> str:
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


def _is_greeting(normalized_text: str) -> bool:
    greetings = {
        "oi",
        "ola",
        "opa",
        "e ai",
        "tudo bem",
        "como vai",
    }
    return normalized_text in greetings


def _looks_technical(question: str) -> bool:
    normalized = question.casefold()
    technical_markers = (" is required", "required field", "validation error")
    return any(marker in normalized for marker in technical_markers)


def _ensure_question_mark(question: str) -> str:
    return question if question.endswith(("?", ".", "!")) else f"{question}?"
