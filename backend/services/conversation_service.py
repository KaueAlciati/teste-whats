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

_MONTH_NAMES = (
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)

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
    del user_name, variant
    emoji = _transaction_emoji(category, description)
    display_description = _display_text(description)
    title = (
        "Despesa registrada"
        if transaction_type == "expense"
        else "Receita registrada"
    )
    amount_emoji = "💸" if transaction_type == "expense" else "💰"
    return (
        f"✅ *{title}*\n\n"
        f"{amount_emoji} *{format_brl(amount)}*\n"
        f"{emoji} {display_description}\n"
        f"📁 {category}\n"
        f"📅 {format_natural_date(transaction_date, current_date)}"
    )


def balance_response(
    balance: Decimal,
    *,
    user_name: str | None = None,
    variant: int = 0,
) -> str:
    del user_name, variant
    return f"💰 *Seu saldo atual*\n\n*{format_brl(balance)}*"


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
    del user_name, variant
    title = "Gastos" if transaction_type == "expense" else "Entradas"
    emoji = "💸" if transaction_type == "expense" else "🟢"
    period_name = _financial_period_name(period)
    if total == Decimal("0"):
        noun = "despesa" if transaction_type == "expense" else "entrada"
        return (
            f"📭 *{title} — {period_name}*\n\n"
            f"Nenhuma {noun} encontrada nesse período."
        )
    return f"{emoji} *{title} — {period_name}*\n\n*{format_brl(total)}*"


def format_largest_expense(
    *,
    amount: Decimal,
    description: str,
    transaction_date: date,
    period_name: str,
) -> str:
    return (
        f"💸 *Maior gasto — {period_name}*\n\n"
        f"*{format_brl(amount)}*\n"
        f"{_display_text(description)}\n"
        f"📅 {transaction_date.strftime('%d/%m/%Y')}"
    )


def format_top_expense_category(
    *,
    category: str,
    total: Decimal,
    period_name: str,
) -> str:
    emoji = _CATEGORY_EMOJIS.get(_normalize_text(category), "📁")
    return (
        f"📊 *Onde você mais gastou — {period_name}*\n\n"
        f"{emoji} *{category}*\n"
        f"*{format_brl(total)}*"
    )


def format_category_expenses(
    *,
    category: str,
    total: Decimal,
    period_name: str,
) -> str:
    emoji = _CATEGORY_EMOJIS.get(_normalize_text(category), "📁")
    return (
        f"{emoji} *Gastos com {_display_text(category)} — {period_name}*\n\n"
        f"*{format_brl(total)}*"
    )


def format_empty_result(*, title: str, message: str) -> str:
    return f"📭 *{title}*\n\n{message}"


def format_period_total(
    *,
    transaction_type: TransactionType,
    total: Decimal,
    period_name: str,
    transactions: list[tuple[date, str, Decimal]] | None = None,
) -> str:
    title = "Gastos" if transaction_type == "expense" else "Entradas"
    noun = "despesa" if transaction_type == "expense" else "entrada"
    if total == Decimal("0"):
        return (
            f"📭 *{title} — {period_name}*\n\n"
            f"Nenhuma {noun} encontrada nesse período."
        )

    emoji = "💸" if transaction_type == "expense" else "🟢"
    lines = [
        f"{emoji} *{title} — {period_name}*",
        "",
        f"Total: *{format_brl(total)}*",
    ]
    rows = (transactions or [])[:5]
    if rows:
        lines.append("")
        lines.extend(
            f"• {item_date.strftime('%d/%m')} · {_display_text(description)} — *{format_brl(amount)}*"
            for item_date, description, amount in rows
        )
    return "\n".join(lines)


def format_latest_transactions(
    *,
    transactions: list[tuple[date, str, Decimal, TransactionType]],
    requested_limit: int,
    transaction_type: TransactionType | None,
    period_name: str | None = None,
    largest_first: bool = False,
) -> str:
    if largest_first:
        title = f"Seus {requested_limit} maiores gastos"
    elif transaction_type == "expense":
        title = f"Seus últimos {requested_limit} gastos"
    elif transaction_type == "income":
        title = f"Suas últimas {requested_limit} entradas"
    else:
        title = f"Suas últimas {requested_limit} movimentações"
    if period_name:
        title = f"Movimentações — {period_name}"

    lines = [f"🧾 *{title}*", ""]
    for index, (item_date, description, amount, item_type) in enumerate(
        transactions[:requested_limit],
        start=1,
    ):
        signal = ""
        if transaction_type is None:
            signal = "−" if item_type == "expense" else "+"
        lines.append(
            f"{index}. {item_date.strftime('%d/%m')} · "
            f"{_display_text(description)} — *{signal}{format_brl(amount)}*"
        )
    return "\n".join(lines)


def format_financial_analysis(
    *,
    income: Decimal,
    expenses: Decimal,
    free_amount: Decimal,
    committed_percentage: float | None,
    score: int,
    level: str,
    explanation: str,
    period_name: str,
) -> str:
    commitment = (
        f"*{f'{committed_percentage:.1f}'.replace('.', ',')}%*"
        if committed_percentage is not None
        else "_indisponível sem renda registrada_"
    )
    level_label = {
        "good": "Boa",
        "attention": "Atenção",
        "critical": "Crítica",
    }.get(level.casefold(), level.capitalize())
    return (
        f"🧠 *Sua situação financeira — {period_name}*\n\n"
        f"🟢 Entradas: *{format_brl(income)}*\n"
        f"🔴 Gastos: *{format_brl(expenses)}*\n"
        f"💰 Saldo livre: *{format_brl(free_amount)}*\n"
        f"📊 Renda comprometida: {commitment}\n\n"
        f"⚠️ *Saúde financeira: {score}/100 — {level_label}*\n"
        f"_score calculado pelos seus dados atuais_\n\n"
        f"{explanation}"
    )


def format_goal_progress(
    *,
    name: str,
    current_amount: Decimal,
    target_amount: Decimal,
    progress: Decimal,
) -> str:
    normalized_progress = max(Decimal("0"), min(Decimal("100"), progress))
    filled = min(10, max(0, int(normalized_progress / Decimal("10"))))
    bar = "█" * filled + "░" * (10 - filled)
    remaining = max(Decimal("0"), target_amount - current_amount)
    return (
        "🎯 *Meta mais próxima*\n\n"
        f"*{name}*\n"
        f"`{bar}` {normalized_progress:.0f}%\n\n"
        f"💰 Guardado: *{format_brl(current_amount)}*\n"
        f"🎯 Objetivo: {format_brl(target_amount)}\n"
        f"⏳ Falta: *{format_brl(remaining)}*"
    )


def format_period_name(
    *,
    start_date: date | None,
    end_date: date | None,
    current_date: date,
    fallback: str,
) -> str:
    if start_date is not None and start_date == end_date:
        if start_date == current_date:
            return "Hoje"
        if start_date == current_date - timedelta(days=1):
            return "Ontem"
        return start_date.strftime("%d/%m")
    if (
        start_date is not None
        and end_date is not None
        and start_date.day == 1
        and start_date.year == end_date.year
        and start_date.month == end_date.month
        and (end_date == current_date or (end_date + timedelta(days=1)).day == 1)
    ):
        month = _MONTH_NAMES[start_date.month]
        return (
            month
            if start_date.year == current_date.year
            else f"{month}/{start_date.year}"
        )
    cleaned = fallback.strip().rstrip(".")
    for prefix in ("em ", "no ", "na ", "nos ", "nas "):
        if cleaned.casefold().startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    return cleaned[:1].upper() + cleaned[1:] if cleaned else "Total"


def _financial_period_name(period: FinancialPeriod) -> str:
    return {
        "today": "Hoje",
        "yesterday": "Ontem",
        "current_week": "Esta semana",
        "current_month": "Este mês",
        "previous_month": "Mês passado",
        "all": "Total",
    }[period]


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


def image_processing_response(variant: int = 0) -> str:
    responses = (
        "Beleza, vou dar uma olhada nesse comprovante 👀",
        "Um instante, vou analisar esse comprovante.",
        "Certo, já vou conferir esse comprovante 👀",
    )
    return responses[variant % len(responses)]


def image_error_response() -> str:
    return "Não consegui analisar esse comprovante agora. Tenta novamente em alguns instantes."


def image_too_large_response() -> str:
    return "Esse arquivo ficou grande demais. Pode enviar uma versão menor?"


def image_unsupported_response() -> str:
    return "Consigo analisar comprovantes em PDF, JPG, JPEG ou PNG. Pode enviar em um desses formatos?"


def receipt_direction_confirmation(amount: Decimal) -> str:
    return (
        f"Consegui identificar um PIX de {format_brl(amount)}, mas não ficou claro "
        "se esse valor foi pago ou recebido.\n\n"
        "Foi um valor que você:\n"
        "1. pagou\n"
        "2. recebeu"
    )


def receipt_identification_confirmation(
    *,
    direction: str,
    amount: Decimal,
    description: str,
    transaction_date: date,
    current_date: date,
) -> str:
    direction_label = {
        "outflow": "Saída",
        "inflow": "Entrada",
        "unknown": "Não identificado",
    }.get(direction, "Não identificado")
    confirmation = (
        "Responda *sim* para salvar ou *não* para descartar."
        if direction in {"outflow", "inflow"}
        else "Responda *paguei* ou *recebi* para confirmar a direção."
    )
    return (
        "Identifiquei este comprovante:\n\n"
        f"💰 Valor: {format_brl(amount)}\n"
        f"📝 Descrição: {_display_text(description)}\n"
        f"📅 Data: {format_natural_date(transaction_date, current_date)}\n"
        f"↕️ Tipo: {direction_label}\n"
        "📂 Categoria: Sem categoria\n\n"
        f"{confirmation}"
    )


def receipt_transaction_confirmation(
    *,
    transaction_type: TransactionType,
    amount: Decimal,
    description: str,
    category: str,
    transaction_date: date,
    current_date: date,
    counterparty: str | None = None,
) -> str:
    if transaction_type == "expense":
        opening = "Vi o comprovante e já deixei salvo pra você 👌"
        title = f"💸 {_display_text(description)} — {format_brl(amount)}"
        party = f"\n👤 Para: {_display_text(counterparty)}" if counterparty else ""
        category_line = f"\n📂 {category}"
    else:
        opening = "Boa, identifiquei esse recebimento e já registrei."
        title = f"💰 {_display_text(description)} — {format_brl(amount)}"
        party = f"\n👤 De: {_display_text(counterparty)}" if counterparty else ""
        category_line = f"\n📂 {category}"

    return (
        f"{opening}\n\n"
        f"{title}{party}{category_line}\n"
        f"📅 {format_natural_date(transaction_date, current_date)}"
    )


def receipt_not_registered_response(
    *,
    document_type: str,
    status: str,
) -> str:
    if status == "pending":
        return "Esse pagamento ainda aparece como pendente. Não registrei nenhuma movimentação."
    if status == "scheduled":
        return "Essa imagem parece mostrar um agendamento. Ainda não registrei nenhuma movimentação."
    if status == "cancelled":
        return "Esse comprovante aparece como cancelado. Não registrei nenhuma movimentação."
    if status == "refunded":
        return "Essa imagem parece envolver devolução ou estorno. Não registrei automaticamente."
    if document_type in {"invoice_image", "unknown"}:
        return (
            "Essa imagem não parece ser um comprovante único e concluído. "
            "Ainda não registrei nada."
        )
    return "Não consegui confirmar os dados desse comprovante com segurança. Não registrei nada."


def pending_receipt_expired_response() -> str:
    return "Essa confirmação expirou. Envie o comprovante novamente para eu analisar."


def pending_receipt_discarded_response() -> str:
    return "Tudo bem, descartei esse comprovante e não registrei nada."


def pending_receipt_amount_updated_response(amount: Decimal) -> str:
    return (
        f"Certo, ajustei o valor para {format_brl(amount)}. "
        "Agora me diga se você pagou ou recebeu esse valor."
    )


def format_audio_understanding(
    transcription: str,
    response: str,
    *,
    variant: int = 0,
) -> str:
    correction_prompts = (
        "Se eu tiver entendido algo errado, é só me corrigir.",
        "Se alguma coisa ficou diferente do que você falou, pode me avisar.",
        "Se eu peguei algum detalhe errado, pode corrigir aqui mesmo.",
    )
    understood = _display_transcription(transcription)
    return (
        f'🎧 Entendi: "{understood}"\n\n'
        f"{response}\n\n"
        f"{correction_prompts[variant % len(correction_prompts)]}"
    )


def format_audio_confirmation(transcription: str) -> str:
    understood = _display_transcription(transcription)
    return f'Eu entendi: "{understood}". Foi isso mesmo?'


def pending_audio_rejected_response() -> str:
    return "Beleza. O que eu entendi errado?"


def pending_audio_expired_response() -> str:
    return "Essa confirmação de áudio expirou. Pode enviar o áudio novamente?"


def format_transaction_correction(
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
    name = _first_name(user_name)
    introductions = (
        "Boa, corrigi aqui 👌",
        "Certo, ajustei pra você.",
        f"Pronto, {name}. Já deixei certo." if name else "Pronto, já deixei certo.",
    )
    emoji = _transaction_emoji(category, description)
    return (
        f"{introductions[variant % len(introductions)]}\n\n"
        f"{emoji} {_display_text(description)} — {format_brl(amount)}\n"
        f"📂 {category}\n"
        f"📅 {format_natural_date(transaction_date, current_date)}"
    )


def format_correction_not_found() -> str:
    return (
        "Não achei um lançamento recente para corrigir. "
        "Me fala qual movimentação você quer alterar."
    )


def format_correction_clarification(detail: str | None = None) -> str:
    if detail:
        return detail
    return "O que você quer corrigir no último lançamento?"


def format_cancel_confirmation(
    *,
    description: str,
    amount: Decimal,
) -> str:
    return (
        "Quer que eu apague o último lançamento de "
        f"{_display_text(description)} — {format_brl(amount)}?"
    )


def _transaction_emoji(category: str, description: str) -> str:
    normalized_description = _normalize_text(description)
    if any(
        term in normalized_description
        for term in ("gasolina", "combustivel", "posto")
    ):
        return "⛽"
    return _CATEGORY_EMOJIS.get(_normalize_text(category), "💰")


def _display_transcription(transcription: str) -> str:
    normalized = " ".join(transcription.split()).replace('"', "'")
    return normalized[:500]


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
