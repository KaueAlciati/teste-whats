import asyncio
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal, engine
from backend.models.user import User
from backend.schemas.financial_intent import FinancialIntent, FinancialPeriod
from backend.services.ai_financial_service import (
    FinancialAIServiceError,
    interpret_financial_message,
)
from backend.services.category_service import find_category_or_default
from backend.services.financial_service import (
    DuplicateWhatsAppMessageError,
    calculate_balance,
    calculate_total_by_type,
    create_transaction,
    get_transaction_by_whatsapp_message_id,
    has_transactions,
)
from backend.services.user_service import get_or_create_whatsapp_user
from backend.services.whatsapp_service import send_text_message


logger = logging.getLogger("uvicorn.error")

AI_ERROR_MESSAGE = (
    "Tive um problema para entender sua mensagem. "
    "Tente novamente em alguns instantes."
)
DATABASE_ERROR_MESSAGE = (
    "Tive um problema para acessar suas finanças. "
    "Tente novamente em alguns instantes."
)
UNKNOWN_MESSAGE = (
    "Posso te ajudar a registrar gastos e receitas ou consultar suas finanças. "
    "Pode falar normalmente, por exemplo: 'gastei 30 reais de gasolina'."
)


async def process_financial_message(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    text: str,
) -> None:
    try:
        response_text = await asyncio.to_thread(
            _process_financial_message,
            whatsapp_phone,
            whatsapp_message_id,
            text,
        )
    except FinancialAIServiceError:
        logger.error("Falha ao interpretar mensagem financeira")
        response_text = AI_ERROR_MESSAGE
    except (SQLAlchemyError, RuntimeError, ValueError, LookupError):
        logger.error("Falha ao processar operação financeira")
        response_text = DATABASE_ERROR_MESSAGE
    except Exception:
        logger.error("Falha inesperada no assistente financeiro")
        response_text = DATABASE_ERROR_MESSAGE

    if response_text:
        await send_text_message(whatsapp_phone, response_text)


def _process_financial_message(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    text: str,
) -> str | None:
    if engine is None:
        raise RuntimeError("Banco de dados indisponível")

    with SessionLocal() as db:
        user = get_or_create_whatsapp_user(db, whatsapp_phone)
        current_date = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        return handle_financial_message(
            db,
            user=user,
            text=text,
            whatsapp_message_id=whatsapp_message_id,
            current_date=current_date,
        )


def handle_financial_message(
    db: Session,
    *,
    user: User,
    text: str,
    whatsapp_message_id: str,
    current_date: date,
) -> str | None:
    if get_transaction_by_whatsapp_message_id(db, whatsapp_message_id) is not None:
        return None

    intent = interpret_financial_message(text, current_date)

    if intent.needs_clarification:
        return intent.clarification_question or "Pode me dar mais detalhes?"

    if intent.action == "create_expense":
        return _create_transaction_response(
            db,
            user=user,
            intent=intent,
            transaction_type="expense",
            whatsapp_message_id=whatsapp_message_id,
            current_date=current_date,
        )

    if intent.action == "create_income":
        return _create_transaction_response(
            db,
            user=user,
            intent=intent,
            transaction_type="income",
            whatsapp_message_id=whatsapp_message_id,
            current_date=current_date,
        )

    if intent.action == "query_balance":
        if not has_transactions(db, user_id=user.id):
            return "Você ainda não possui movimentações registradas."
        balance = calculate_balance(db, user_id=user.id)
        return f"💰 Seu saldo atual é {_format_currency(balance)}."

    if intent.action == "query_expenses":
        return _query_total_response(
            db,
            user=user,
            transaction_type="expense",
            period=intent.period or "all",
            current_date=current_date,
        )

    if intent.action == "query_income":
        return _query_total_response(
            db,
            user=user,
            transaction_type="income",
            period=intent.period or "all",
            current_date=current_date,
        )

    return UNKNOWN_MESSAGE


def _create_transaction_response(
    db: Session,
    *,
    user: User,
    intent: FinancialIntent,
    transaction_type: str,
    whatsapp_message_id: str,
    current_date: date,
) -> str | None:
    if intent.amount is None:
        return "Qual foi o valor da movimentação?"

    description = (intent.description or "").strip()
    if not description:
        return "Qual foi a descrição da movimentação?"
    if len(description) > 255:
        return "Pode resumir a descrição em até 255 caracteres?"

    try:
        amount = Decimal(str(intent.amount))
    except InvalidOperation:
        return "Não consegui entender o valor. Pode informá-lo novamente?"
    if not amount.is_finite() or amount <= 0:
        return "O valor precisa ser maior que zero."

    transaction_date = _parse_transaction_date(
        intent.transaction_date,
        current_date,
    )
    if transaction_date is None:
        return "Não consegui entender a data. Pode informá-la novamente?"

    payment_method = (intent.payment_method or "").strip() or None
    if payment_method is not None and len(payment_method) > 50:
        return "Pode resumir a forma de pagamento em até 50 caracteres?"

    category = find_category_or_default(
        db,
        user_id=user.id,
        category_name=intent.category,
        transaction_type=transaction_type,
    )

    try:
        transaction = create_transaction(
            db,
            user_id=user.id,
            type=transaction_type,
            amount=amount,
            description=description,
            category_id=category.id,
            transaction_date=transaction_date,
            payment_method=payment_method,
            source="whatsapp_text",
            whatsapp_message_id=whatsapp_message_id,
        )
    except DuplicateWhatsAppMessageError:
        return None

    title = "Gasto registrado" if transaction_type == "expense" else "Receita registrada"
    return (
        f"✅ {title}\n\n"
        f"💰 {_format_currency(transaction.amount)}\n"
        f"📝 {transaction.description.strip().capitalize()}\n"
        f"🗂️ {category.name}\n"
        f"📅 {transaction.transaction_date.strftime('%d/%m/%Y')}"
    )


def _query_total_response(
    db: Session,
    *,
    user: User,
    transaction_type: str,
    period: FinancialPeriod,
    current_date: date,
) -> str:
    start_date, end_date = _period_bounds(period, current_date)
    total = calculate_total_by_type(
        db,
        user_id=user.id,
        transaction_type=transaction_type,
        start_date=start_date,
        end_date=end_date,
    )
    period_label = _period_label(period)

    if transaction_type == "expense":
        if total == 0:
            return f"Você não teve gastos {period_label}."
        return f"📊 Você gastou {_format_currency(total)} {period_label}."

    if total == 0:
        return f"Você não recebeu receitas {period_label}."
    return f"💰 Você recebeu {_format_currency(total)} {period_label}."


def _parse_transaction_date(
    value: str | None,
    current_date: date,
) -> date | None:
    if not value:
        return current_date
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _period_bounds(
    period: FinancialPeriod,
    current_date: date,
) -> tuple[date | None, date | None]:
    if period == "today":
        return current_date, current_date
    if period == "yesterday":
        yesterday = current_date - timedelta(days=1)
        return yesterday, yesterday
    if period == "current_week":
        return current_date - timedelta(days=current_date.weekday()), current_date
    if period == "current_month":
        return current_date.replace(day=1), current_date
    if period == "previous_month":
        current_month_start = current_date.replace(day=1)
        previous_month_end = current_month_start - timedelta(days=1)
        return previous_month_end.replace(day=1), previous_month_end
    return None, None


def _period_label(period: FinancialPeriod) -> str:
    labels = {
        "today": "hoje",
        "yesterday": "ontem",
        "current_week": "nesta semana",
        "current_month": "neste mês",
        "previous_month": "no mês passado",
        "all": "no total",
    }
    return labels[period]


def _format_currency(value: Decimal) -> str:
    formatted = f"{value.quantize(Decimal('0.01')):,.2f}"
    formatted = formatted.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"
