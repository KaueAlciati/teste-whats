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
from backend.services.audio_transcription_service import (
    AudioTranscriptionError,
    transcribe_audio,
)
from backend.services.category_service import find_category_or_default
from backend.services.conversation_service import (
    ai_error_response,
    audio_empty_response,
    audio_error_response,
    audio_processing_response,
    audio_too_large_response,
    balance_response,
    clarification_response,
    no_transactions_response,
    non_financial_response,
    operation_error_response,
    response_variant,
    total_response,
    transaction_confirmation,
)
from backend.services.financial_service import (
    DuplicateWhatsAppMessageError,
    calculate_balance,
    calculate_total_by_type,
    create_transaction,
    get_transaction_by_whatsapp_message_id,
    has_transactions,
)
from backend.services.user_service import get_or_create_whatsapp_user
from backend.services.whatsapp_media_service import (
    WhatsAppMediaError,
    WhatsAppMediaTooLargeError,
    download_whatsapp_media,
)
from backend.services.whatsapp_service import send_text_message


logger = logging.getLogger("uvicorn.error")

AI_ERROR_MESSAGE = ai_error_response()
DATABASE_ERROR_MESSAGE = operation_error_response()
UNKNOWN_MESSAGE = non_financial_response("")


async def process_financial_audio_message(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    media_id: str,
    mime_type: str | None,
) -> None:
    try:
        already_processed = await asyncio.to_thread(
            _message_already_processed,
            whatsapp_message_id,
        )
    except Exception as exc:
        logger.error(
            "Falha ao verificar duplicidade do áudio: tipo=%s",
            type(exc).__name__,
        )
        already_processed = False

    if already_processed:
        return

    variant = response_variant(whatsapp_message_id)
    await send_text_message(
        whatsapp_phone,
        audio_processing_response(variant),
    )

    try:
        media = await download_whatsapp_media(
            media_id,
            fallback_mime_type=mime_type,
        )
        transcription = await transcribe_audio(
            media.content,
            filename=media.filename,
            mime_type=media.mime_type,
        )
    except WhatsAppMediaTooLargeError:
        logger.error("Áudio do WhatsApp excedeu o tamanho máximo")
        await send_text_message(whatsapp_phone, audio_too_large_response())
        return
    except (WhatsAppMediaError, AudioTranscriptionError) as exc:
        logger.error("Falha ao processar áudio: tipo=%s", type(exc).__name__)
        await send_text_message(whatsapp_phone, audio_error_response())
        return
    except Exception as exc:
        logger.error(
            "Falha inesperada ao processar áudio: tipo=%s",
            type(exc).__name__,
        )
        await send_text_message(whatsapp_phone, audio_error_response())
        return

    if not transcription.strip():
        await send_text_message(whatsapp_phone, audio_empty_response())
        return

    await process_financial_message(
        whatsapp_phone,
        whatsapp_message_id,
        transcription,
        source="whatsapp_audio",
    )


async def process_financial_message(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    text: str,
    *,
    source: str = "whatsapp_text",
) -> None:
    try:
        response_text = await asyncio.to_thread(
            _process_financial_message,
            whatsapp_phone,
            whatsapp_message_id,
            text,
            source,
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
    source: str = "whatsapp_text",
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
            source=source,
        )


def handle_financial_message(
    db: Session,
    *,
    user: User,
    text: str,
    whatsapp_message_id: str,
    current_date: date,
    source: str = "whatsapp_text",
) -> str | None:
    if get_transaction_by_whatsapp_message_id(db, whatsapp_message_id) is not None:
        return None

    intent = interpret_financial_message(text, current_date)
    variant = response_variant(whatsapp_message_id)

    if intent.needs_clarification:
        return clarification_response(
            action=intent.action,
            question=intent.clarification_question,
            missing_amount=intent.amount is None,
            missing_description=not bool((intent.description or "").strip()),
        )

    if intent.action == "create_expense":
        return _create_transaction_response(
            db,
            user=user,
            intent=intent,
            transaction_type="expense",
            whatsapp_message_id=whatsapp_message_id,
            current_date=current_date,
            variant=variant,
            source=source,
        )

    if intent.action == "create_income":
        return _create_transaction_response(
            db,
            user=user,
            intent=intent,
            transaction_type="income",
            whatsapp_message_id=whatsapp_message_id,
            current_date=current_date,
            variant=variant,
            source=source,
        )

    if intent.action == "query_balance":
        if not has_transactions(db, user_id=user.id):
            return no_transactions_response(
                user_name=user.name,
                variant=variant,
            )
        balance = calculate_balance(db, user_id=user.id)
        return balance_response(
            balance,
            user_name=user.name,
            variant=variant,
        )

    if intent.action == "query_expenses":
        return _query_total_response(
            db,
            user=user,
            transaction_type="expense",
            period=intent.period or "all",
            current_date=current_date,
            variant=variant,
        )

    if intent.action == "query_income":
        return _query_total_response(
            db,
            user=user,
            transaction_type="income",
            period=intent.period or "all",
            current_date=current_date,
            variant=variant,
        )

    return non_financial_response(
        text,
        user_name=user.name,
        variant=variant,
    )


def _create_transaction_response(
    db: Session,
    *,
    user: User,
    intent: FinancialIntent,
    transaction_type: str,
    whatsapp_message_id: str,
    current_date: date,
    variant: int,
    source: str,
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
            source=source,
            whatsapp_message_id=whatsapp_message_id,
        )
    except DuplicateWhatsAppMessageError:
        return None

    return transaction_confirmation(
        transaction_type=transaction_type,
        amount=transaction.amount,
        description=transaction.description,
        category=category.name,
        transaction_date=transaction.transaction_date,
        current_date=current_date,
        user_name=user.name,
        variant=variant,
    )


def _message_already_processed(whatsapp_message_id: str) -> bool:
    if engine is None:
        return False
    with SessionLocal() as db:
        transaction = get_transaction_by_whatsapp_message_id(
            db,
            whatsapp_message_id,
        )
        return transaction is not None


def _query_total_response(
    db: Session,
    *,
    user: User,
    transaction_type: str,
    period: FinancialPeriod,
    current_date: date,
    variant: int,
) -> str:
    start_date, end_date = _period_bounds(period, current_date)
    total = calculate_total_by_type(
        db,
        user_id=user.id,
        transaction_type=transaction_type,
        start_date=start_date,
        end_date=end_date,
    )
    return total_response(
        transaction_type=transaction_type,
        total=total,
        period=period,
        user_name=user.name,
        variant=variant,
    )


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
