import asyncio
import logging
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal, engine
from backend.models.financial_transaction import FinancialTransaction
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
from backend.services.category_service import (
    find_category_or_default,
    find_existing_category,
)
from backend.services.conversation_service import (
    ai_error_response,
    audio_empty_response,
    audio_error_response,
    audio_processing_response,
    audio_too_large_response,
    balance_response,
    clarification_response,
    format_audio_confirmation,
    format_audio_understanding,
    format_cancel_confirmation,
    format_correction_clarification,
    format_correction_not_found,
    format_transaction_correction,
    no_transactions_response,
    non_financial_response,
    operation_error_response,
    pending_audio_expired_response,
    pending_audio_rejected_response,
    response_variant,
    total_response,
    transaction_confirmation,
)
from backend.services.financial_service import (
    DuplicateWhatsAppMessageError,
    calculate_balance,
    calculate_total_by_type,
    create_transaction,
    get_latest_transaction_for_user,
    get_transaction_by_whatsapp_message_id,
    has_transactions,
    update_transaction,
)
from backend.services.goal_whatsapp_service import handle_goal_whatsapp_message
from backend.services.pending_audio_confirmation_service import (
    append_pending_audio_complement,
    create_pending_audio_confirmation,
    delete_pending_audio_confirmation,
    get_latest_pending_audio_for_user,
    get_pending_audio_by_message_id,
    pending_audio_is_expired,
)
from backend.services.receipt_assistant_service import handle_pending_receipt_reply
from backend.services.statement_export_service import (
    ExportedStatement,
    generate_statement,
    resolve_whatsapp_statement_request,
)
from backend.services.user_service import get_or_create_whatsapp_user
from backend.services.whatsapp_media_service import (
    WhatsAppMediaError,
    WhatsAppMediaTooLargeError,
    download_whatsapp_media,
)
from backend.services.whatsapp_service import send_document_message, send_text_message


logger = logging.getLogger("uvicorn.error")

AI_ERROR_MESSAGE = ai_error_response()
DATABASE_ERROR_MESSAGE = operation_error_response()
UNKNOWN_MESSAGE = non_financial_response("")

CORRECTION_WINDOW = timedelta(minutes=15)
AUDIO_AUTO_REGISTER_CONFIDENCE_THRESHOLD = 0.75
TYPE_CORRECTION_CONFIDENCE_THRESHOLD = 0.90


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
        audio_transcription=transcription,
    )


async def process_financial_message(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    text: str,
    *,
    source: str = "whatsapp_text",
    audio_transcription: str | None = None,
) -> None:
    try:
        response = await asyncio.to_thread(
            _process_financial_message,
            whatsapp_phone,
            whatsapp_message_id,
            text,
            source,
            audio_transcription,
        )
    except FinancialAIServiceError:
        logger.error("Falha ao interpretar mensagem financeira")
        response = AI_ERROR_MESSAGE
    except (SQLAlchemyError, RuntimeError, ValueError, LookupError):
        logger.error("Falha ao processar operação financeira")
        response = DATABASE_ERROR_MESSAGE
    except Exception:
        logger.error("Falha inesperada no assistente financeiro")
        response = DATABASE_ERROR_MESSAGE

    if isinstance(response, ExportedStatement):
        sent = await send_document_message(
            whatsapp_phone,
            content=response.content,
            filename=response.filename,
            mime_type=response.media_type,
            caption=f"Extrato FinControl AI · {response.period_label}",
        )
        if not sent:
            await send_text_message(
                whatsapp_phone,
                "Não consegui enviar seu extrato agora. Tenta novamente em alguns instantes.",
            )
        return

    if response:
        await send_text_message(whatsapp_phone, response)


def _process_financial_message(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    text: str,
    source: str = "whatsapp_text",
    audio_transcription: str | None = None,
) -> str | ExportedStatement | None:
    if engine is None:
        raise RuntimeError("Banco de dados indisponível")

    with SessionLocal() as db:
        user = get_or_create_whatsapp_user(db, whatsapp_phone)
        processing_time = datetime.now(ZoneInfo("America/Sao_Paulo"))
        return handle_financial_message(
            db,
            user=user,
            text=text,
            whatsapp_message_id=whatsapp_message_id,
            current_date=processing_time.date(),
            source=source,
            current_datetime=processing_time,
            audio_transcription=audio_transcription,
        )


def handle_financial_message(
    db: Session,
    *,
    user: User,
    text: str,
    whatsapp_message_id: str,
    current_date: date,
    source: str = "whatsapp_text",
    current_datetime: datetime | None = None,
    audio_transcription: str | None = None,
    confirmed_audio: bool = False,
    pending_audio_correction: str | None = None,
    skip_pending_context: bool = False,
) -> str | ExportedStatement | None:
    if get_transaction_by_whatsapp_message_id(db, whatsapp_message_id) is not None:
        return None

    processing_time = current_datetime or datetime.now(
        ZoneInfo("America/Sao_Paulo")
    )
    variant = response_variant(whatsapp_message_id)

    statement_request = resolve_whatsapp_statement_request(
        text,
        current_date=current_date,
    )
    if statement_request is not None:
        exported = generate_statement(
            db,
            user_id=user.id,
            period=statement_request,
            export_format="xlsx",
        )
        if exported is None:
            item = (
                "gastos"
                if statement_request.transaction_type == "expense"
                else "movimentações"
            )
            return (
                f"Não encontrei {item} no período solicitado, "
                "então não gerei um arquivo vazio."
            )
        return exported

    if not skip_pending_context:
        audio_pending_handled, audio_pending_response = _handle_pending_audio_reply(
            db,
            user=user,
            text=text,
            current_date=current_date,
            current_time=processing_time,
        )
        if audio_pending_handled:
            return audio_pending_response

        pending_reply = handle_pending_receipt_reply(
            db,
            user=user,
            text=text,
            current_date=current_date,
            current_time=processing_time,
        )
        if pending_reply.handled:
            return pending_reply.response

    goal_handled, goal_response = handle_goal_whatsapp_message(
        db,
        user=user,
        text=text,
        source=source,
        current_time=processing_time,
    )
    if goal_handled:
        if (
            goal_response
            and source == "whatsapp_audio"
            and audio_transcription
        ):
            return format_audio_understanding(
                audio_transcription,
                goal_response,
                variant=variant,
            )
        return goal_response

    latest_transaction = get_latest_transaction_for_user(
        db,
        user_id=user.id,
        created_after=processing_time - CORRECTION_WINDOW,
    )
    latest_context = _latest_transaction_context(
        latest_transaction,
        current_date=current_date,
    )
    intent = interpret_financial_message(
        text,
        current_date,
        last_transaction_context=None if confirmed_audio else latest_context,
        pending_audio_correction=pending_audio_correction,
    )
    if confirmed_audio:
        intent = _complete_confirmed_audio_intent(
            intent,
            transcription=text,
            complement=pending_audio_correction,
        )
    if (
        source == "whatsapp_audio"
        and audio_transcription
        and intent.action in {"create_expense", "create_income"}
        and intent.needs_clarification
        and not confirmed_audio
    ):
        create_pending_audio_confirmation(
            db,
            user_id=user.id,
            original_whatsapp_message_id=whatsapp_message_id,
            transcription=audio_transcription,
            current_time=processing_time,
        )
        question = clarification_response(
            action=intent.action,
            question=intent.clarification_question,
            missing_amount=intent.amount is None,
            missing_description=not bool((intent.description or "").strip()),
        )
        return format_audio_understanding(
            audio_transcription,
            question,
            variant=variant,
        )

    if (
        source == "whatsapp_audio"
        and audio_transcription
        and intent.action
        in {"create_expense", "create_income", "correct_last_transaction"}
        and intent.confidence < AUDIO_AUTO_REGISTER_CONFIDENCE_THRESHOLD
        and not confirmed_audio
    ):
        create_pending_audio_confirmation(
            db,
            user_id=user.id,
            original_whatsapp_message_id=whatsapp_message_id,
            transcription=audio_transcription,
            current_time=processing_time,
        )
        return format_audio_confirmation(audio_transcription)

    if confirmed_audio and intent.action in {
        "correct_last_transaction",
        "cancel_last_transaction",
    }:
        return format_correction_clarification(
            "Não consegui aplicar essa correção ao áudio. Pode me dizer a movimentação completa?"
        )

    def present(response: str | None) -> str | None:
        if response is None:
            return None
        if source == "whatsapp_audio" and audio_transcription:
            return format_audio_understanding(
                audio_transcription,
                response,
                variant=variant,
            )
        return response

    if intent.needs_clarification:
        return present(
            clarification_response(
                action=intent.action,
                question=intent.clarification_question,
                missing_amount=intent.amount is None,
                missing_description=not bool((intent.description or "").strip()),
            )
        )

    if intent.action == "create_expense":
        return present(
            _create_transaction_response(
                db,
                user=user,
                intent=intent,
                transaction_type="expense",
                whatsapp_message_id=whatsapp_message_id,
                current_date=current_date,
                variant=variant,
                source=source,
            )
        )

    if intent.action == "create_income":
        return present(
            _create_transaction_response(
                db,
                user=user,
                intent=intent,
                transaction_type="income",
                whatsapp_message_id=whatsapp_message_id,
                current_date=current_date,
                variant=variant,
                source=source,
            )
        )

    if intent.action == "correct_last_transaction":
        return present(
            _correct_transaction_response(
                db,
                user=user,
                intent=intent,
                transaction=latest_transaction,
                current_date=current_date,
                variant=variant,
            )
        )

    if intent.action == "cancel_last_transaction":
        if latest_transaction is None:
            return present(format_correction_not_found())
        return present(
            format_cancel_confirmation(
                description=latest_transaction.description,
                amount=latest_transaction.amount,
            )
        )

    if intent.action == "query_balance":
        if not has_transactions(db, user_id=user.id):
            return present(
                no_transactions_response(
                    user_name=user.name,
                    variant=variant,
                )
            )
        balance = calculate_balance(db, user_id=user.id)
        return present(
            balance_response(
                balance,
                user_name=user.name,
                variant=variant,
            )
        )

    if intent.action == "query_expenses":
        return present(
            _query_total_response(
                db,
                user=user,
                transaction_type="expense",
                period=intent.period or "all",
                current_date=current_date,
                variant=variant,
            )
        )

    if intent.action == "query_income":
        return present(
            _query_total_response(
                db,
                user=user,
                transaction_type="income",
                period=intent.period or "all",
                current_date=current_date,
                variant=variant,
            )
        )

    return present(
        non_financial_response(
            text,
            user_name=user.name,
            variant=variant,
        )
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


def _correct_transaction_response(
    db: Session,
    *,
    user: User,
    intent: FinancialIntent,
    transaction: FinancialTransaction | None,
    current_date: date,
    variant: int,
) -> str:
    if transaction is None:
        return format_correction_not_found()

    amount: Decimal | None = None
    description: str | None = None
    category = None
    transaction_date: date | None = None
    payment_method: str | None = None
    transaction_type = intent.type
    changed_fields: set[str] = set()

    if intent.amount is not None:
        try:
            amount = Decimal(str(intent.amount))
        except InvalidOperation:
            return format_correction_clarification(
                "Não consegui entender o novo valor. Pode me dizer novamente?"
            )
        if not amount.is_finite() or amount <= 0:
            return format_correction_clarification(
                "O novo valor precisa ser maior que zero."
            )
        changed_fields.add("amount")

    if intent.description is not None:
        description = intent.description.strip()
        if not description or len(description) > 255:
            return format_correction_clarification(
                "Pode me dizer uma descrição curta para essa correção?"
            )
        changed_fields.add("description")

    if transaction_type is not None:
        if intent.confidence < TYPE_CORRECTION_CONFIDENCE_THRESHOLD:
            return format_correction_clarification(
                "Você quer mesmo trocar o tipo dessa movimentação?"
            )
        changed_fields.add("type")

    final_type = transaction_type or transaction.type
    if intent.category is not None:
        category = find_existing_category(
            db,
            user_id=user.id,
            category_name=intent.category,
            transaction_type=final_type,
        )
        if category is None:
            return format_correction_clarification(
                "Não encontrei essa categoria. Qual categoria existente você quer usar?"
            )
        changed_fields.add("category")
    elif transaction_type is not None and transaction_type != transaction.type:
        category = find_category_or_default(
            db,
            user_id=user.id,
            category_name="Outros",
            transaction_type=final_type,
        )
        changed_fields.add("category")

    if intent.transaction_date is not None:
        transaction_date = _parse_transaction_date(
            intent.transaction_date,
            current_date,
        )
        if transaction_date is None:
            return format_correction_clarification(
                "Não consegui entender a nova data. Pode me dizer novamente?"
            )
        changed_fields.add("transaction_date")

    if intent.payment_method is not None:
        payment_method = intent.payment_method.strip()
        if not payment_method or len(payment_method) > 50:
            return format_correction_clarification(
                "Pode resumir a nova forma de pagamento?"
            )
        changed_fields.add("payment_method")

    if not changed_fields:
        return format_correction_clarification()

    try:
        updated_transaction = update_transaction(
            db,
            transaction=transaction,
            user_id=user.id,
            amount=amount,
            description=description,
            category=category,
            transaction_date=transaction_date,
            payment_method=payment_method,
            type=transaction_type,
        )
    except PermissionError:
        return format_correction_not_found()
    except ValueError:
        return format_correction_clarification(
            "Não consegui aplicar essa correção. Pode conferir os dados?"
        )

    logger.info(
        "Transação corrigida: transaction_id=%s campos=%s",
        updated_transaction.id,
        ",".join(sorted(changed_fields)),
    )

    category_name = (
        category.name
        if category is not None
        else (
            updated_transaction.category.name
            if updated_transaction.category is not None
            else "Outros"
        )
    )
    return format_transaction_correction(
        transaction_type=updated_transaction.type,
        amount=updated_transaction.amount,
        description=updated_transaction.description,
        category=category_name,
        transaction_date=updated_transaction.transaction_date,
        current_date=current_date,
        user_name=user.name,
        variant=variant,
    )


def _latest_transaction_context(
    transaction: FinancialTransaction | None,
    *,
    current_date: date,
) -> str | None:
    if transaction is None:
        return None

    transaction_type = "despesa" if transaction.type == "expense" else "receita"
    category_name = (
        transaction.category.name if transaction.category is not None else "Outros"
    )
    date_label = (
        "hoje"
        if transaction.transaction_date == current_date
        else transaction.transaction_date.isoformat()
    )
    return (
        f"tipo={transaction_type}; valor={transaction.amount}; "
        f"descrição={transaction.description}; categoria={category_name}; "
        f"data={date_label}."
    )


def _handle_pending_audio_reply(
    db: Session,
    *,
    user: User,
    text: str,
    current_date: date,
    current_time: datetime,
) -> tuple[bool, str | None]:
    pending = get_latest_pending_audio_for_user(db, user_id=user.id)
    if pending is None:
        return False, None

    if pending_audio_is_expired(pending, current_time=current_time):
        delete_pending_audio_confirmation(
            db,
            pending=pending,
            user_id=user.id,
        )
        return True, pending_audio_expired_response()

    reply_type = _classify_pending_audio_reply(text)
    if reply_type is None:
        if not text.strip():
            return False, None
        reply_type = "complement"

    if reply_type == "negative":
        delete_pending_audio_confirmation(
            db,
            pending=pending,
            user_id=user.id,
        )
        return True, pending_audio_rejected_response()

    correction = text if reply_type in {"correction", "complement"} else None
    response = handle_financial_message(
        db,
        user=user,
        text=pending.transcription,
        whatsapp_message_id=pending.original_whatsapp_message_id,
        current_date=current_date,
        source="whatsapp_audio",
        current_datetime=current_time,
        audio_transcription=pending.transcription,
        confirmed_audio=True,
        pending_audio_correction=correction,
        skip_pending_context=True,
    )
    transaction = get_transaction_by_whatsapp_message_id(
        db,
        pending.original_whatsapp_message_id,
    )
    if transaction is not None:
        delete_pending_audio_confirmation(
            db,
            pending=pending,
            user_id=user.id,
        )
    elif correction is not None:
        append_pending_audio_complement(
            db,
            pending=pending,
            user_id=user.id,
            complement=correction,
        )
    return True, response


def _complete_confirmed_audio_intent(
    intent: FinancialIntent,
    *,
    transcription: str,
    complement: str | None,
) -> FinancialIntent:
    if intent.action not in {"create_expense", "create_income"}:
        return intent

    amount = intent.amount
    if amount is None:
        amount = _extract_explicit_audio_amount(complement or "")
        if amount is None:
            amount = _extract_explicit_audio_amount(transcription)

    description = (intent.description or "").strip()
    if amount is None or not description:
        return intent

    return intent.model_copy(
        update={
            "amount": amount,
            "needs_clarification": False,
            "clarification_question": None,
        }
    )


def _extract_explicit_audio_amount(text: str) -> float | None:
    amount_token = r"[0-9][0-9.,]*"
    patterns = (
        rf"r\$\s*({amount_token})",
        rf"({amount_token})\s*(?:reais?|conto)\b",
        rf"\b(?:comprei|gastei|paguei|recebi|ganhei)\s+({amount_token})\b",
    )
    normalized = text.casefold()
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match is None:
            continue
        raw_amount = match.group(1)
        if "," in raw_amount:
            raw_amount = raw_amount.replace(".", "").replace(",", ".")
        elif raw_amount.count(".") == 1:
            integer_part, decimal_part = raw_amount.split(".")
            if len(decimal_part) == 3:
                raw_amount = integer_part + decimal_part
        elif raw_amount.count(".") > 1:
            raw_amount = raw_amount.replace(".", "")
        try:
            amount = Decimal(raw_amount)
        except InvalidOperation:
            continue
        if amount.is_finite() and amount > 0:
            return float(amount)
    return None


def _classify_pending_audio_reply(text: str) -> str | None:
    normalized = _normalize_confirmation_text(text)
    positive_replies = {
        "sim",
        "isso",
        "isso mesmo",
        "correto",
        "certo",
        "e isso",
        "exatamente",
        "pode",
        "pode registrar",
        "isso ai",
    }
    negative_replies = {
        "nao",
        "errado",
        "entendeu errado",
        "nao foi isso",
    }
    if normalized in positive_replies:
        return "positive"
    if normalized in negative_replies:
        return "negative"
    if normalized.startswith(
        (
            "nao ",
            "errado ",
            "entendeu errado ",
            "nao foi isso ",
            "na verdade ",
        )
    ):
        return "correction"
    return None


def _normalize_confirmation_text(value: str) -> str:
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


def _message_already_processed(whatsapp_message_id: str) -> bool:
    if engine is None:
        return False
    with SessionLocal() as db:
        transaction = get_transaction_by_whatsapp_message_id(
            db,
            whatsapp_message_id,
        )
        pending_audio = get_pending_audio_by_message_id(
            db,
            whatsapp_message_id,
        )
        return transaction is not None or pending_audio is not None


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
