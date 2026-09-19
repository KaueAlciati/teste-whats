import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal, engine
from backend.models.pending_receipt import PendingReceipt
from backend.models.user import User
from backend.schemas.receipt_extraction import ReceiptDirection, ReceiptExtraction
from backend.services.category_service import find_category_or_default
from backend.services.conversation_service import (
    image_error_response,
    image_processing_response,
    image_too_large_response,
    image_unsupported_response,
    pending_receipt_amount_updated_response,
    pending_receipt_discarded_response,
    pending_receipt_expired_response,
    receipt_direction_confirmation,
    receipt_not_registered_response,
    receipt_transaction_confirmation,
    response_variant,
)
from backend.services.financial_service import (
    DuplicateWhatsAppMessageError,
    create_transaction,
    get_transaction_by_whatsapp_message_id,
)
from backend.services.image_understanding_service import (
    ImageUnderstandingError,
    analyze_receipt_image,
)
from backend.services.pending_receipt_service import (
    create_pending_receipt,
    delete_pending_receipt,
    get_latest_pending_receipt_for_user,
    get_pending_receipt_by_message_id,
    pending_receipt_is_expired,
    update_pending_receipt_amount,
)
from backend.services.user_service import get_or_create_whatsapp_user
from backend.services.whatsapp_media_service import (
    WhatsAppMediaError,
    WhatsAppMediaTooLargeError,
    WhatsAppMediaUnsupportedTypeError,
    download_whatsapp_media,
)
from backend.services.whatsapp_service import send_text_message


logger = logging.getLogger("uvicorn.error")

AUTO_REGISTER_CONFIDENCE = 0.90
SUPPORTED_RECEIPT_DOCUMENTS = {
    "pix_receipt",
    "bank_transfer_receipt",
    "payment_receipt",
    "purchase_receipt",
}


@dataclass(frozen=True)
class ValidatedReceipt:
    amount: Decimal
    transaction_date: date
    direction: ReceiptDirection


@dataclass(frozen=True)
class PendingReplyResult:
    handled: bool
    response: str | None = None


async def process_financial_image_message(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    media_id: str,
    mime_type: str | None,
    caption: str | None,
) -> None:
    try:
        already_handled = await asyncio.to_thread(
            _image_message_already_handled,
            whatsapp_message_id,
        )
    except Exception as exc:
        logger.error(
            "Falha ao verificar duplicidade da imagem: tipo=%s",
            type(exc).__name__,
        )
        already_handled = False

    if already_handled:
        return

    logger.info("media_id encontrado")
    await send_text_message(
        whatsapp_phone,
        image_processing_response(response_variant(whatsapp_message_id)),
    )

    try:
        media = await download_whatsapp_media(
            media_id,
            fallback_mime_type=mime_type,
            media_kind="image",
        )
        logger.info(
            "Download da imagem concluído: mime_type=%s image_size_bytes=%s",
            media.mime_type,
            len(media.content),
        )
        user_name = await asyncio.to_thread(_get_user_name, whatsapp_phone)
        processing_time = datetime.now(ZoneInfo("America/Sao_Paulo"))
        extraction = await asyncio.to_thread(
            analyze_receipt_image,
            media.content,
            mime_type=media.mime_type,
            current_date=processing_time.date(),
            caption=caption,
            user_name=user_name,
        )
        response = await asyncio.to_thread(
            _process_receipt_extraction,
            whatsapp_phone,
            whatsapp_message_id,
            extraction,
            processing_time,
            caption,
        )
    except WhatsAppMediaTooLargeError:
        logger.error("Imagem do WhatsApp excedeu o tamanho máximo")
        response = image_too_large_response()
    except WhatsAppMediaUnsupportedTypeError:
        logger.error("Imagem do WhatsApp possui formato não suportado")
        response = image_unsupported_response()
    except (WhatsAppMediaError, ImageUnderstandingError) as exc:
        logger.error("Falha ao processar imagem: tipo=%s", type(exc).__name__)
        response = image_error_response()
    except (SQLAlchemyError, RuntimeError, ValueError, LookupError) as exc:
        logger.error(
            "Falha ao registrar análise de imagem: tipo=%s",
            type(exc).__name__,
        )
        response = image_error_response()
    except Exception as exc:
        logger.exception(
            "Falha inesperada ao processar imagem: tipo=%s",
            type(exc).__name__,
        )
        response = image_error_response()

    if response:
        await send_text_message(whatsapp_phone, response)


def handle_pending_receipt_reply(
    db: Session,
    *,
    user: User,
    text: str,
    current_date: date,
    current_time: datetime,
) -> PendingReplyResult:
    reply_type, corrected_amount = _classify_pending_reply(text)
    if reply_type is None:
        return PendingReplyResult(handled=False)

    pending = get_latest_pending_receipt_for_user(db, user_id=user.id)
    if pending is None:
        return PendingReplyResult(handled=False)

    if pending_receipt_is_expired(pending, current_time=current_time):
        delete_pending_receipt(db, pending=pending, user_id=user.id)
        return PendingReplyResult(
            handled=True,
            response=pending_receipt_expired_response(),
        )

    if reply_type == "discard":
        delete_pending_receipt(db, pending=pending, user_id=user.id)
        return PendingReplyResult(
            handled=True,
            response=pending_receipt_discarded_response(),
        )

    if reply_type == "amount" and corrected_amount is not None:
        update_pending_receipt_amount(
            db,
            pending=pending,
            user_id=user.id,
            amount=f"{corrected_amount:.2f}",
        )
        return PendingReplyResult(
            handled=True,
            response=pending_receipt_amount_updated_response(corrected_amount),
        )

    extraction = ReceiptExtraction.model_validate(pending.extracted_data)
    direction: ReceiptDirection = (
        "outflow" if reply_type == "outflow" else "inflow"
    )
    response = _register_validated_receipt(
        db,
        user=user,
        whatsapp_message_id=pending.whatsapp_message_id,
        extraction=extraction,
        current_date=current_date,
        direction_override=direction,
        allow_direction_confirmation=True,
    )
    if response is None:
        response = receipt_not_registered_response(
            document_type=extraction.document_type,
            status=extraction.status,
        )

    delete_pending_receipt(db, pending=pending, user_id=user.id)
    return PendingReplyResult(handled=True, response=response)


def _process_receipt_extraction(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    extraction: ReceiptExtraction,
    processing_time: datetime,
    caption: str | None = None,
) -> str | None:
    if engine is None:
        raise RuntimeError("Banco de dados indisponível")

    with SessionLocal() as db:
        user = get_or_create_whatsapp_user(db, whatsapp_phone)
        if (
            get_transaction_by_whatsapp_message_id(db, whatsapp_message_id)
            is not None
        ):
            return None
        if get_pending_receipt_by_message_id(db, whatsapp_message_id) is not None:
            return None

        caption_direction = _direction_from_caption(caption)
        direction_override: ReceiptDirection | None = None
        allow_caption_confirmation = False
        direction_conflict = False
        if caption_direction in {"outflow", "inflow"}:
            if extraction.direction == "unknown":
                direction_override = caption_direction
                allow_caption_confirmation = True
            elif extraction.direction != caption_direction:
                direction_conflict = True

        response = None
        if not direction_conflict:
            response = _register_validated_receipt(
                db,
                user=user,
                whatsapp_message_id=whatsapp_message_id,
                extraction=extraction,
                current_date=processing_time.date(),
                direction_override=direction_override,
                allow_direction_confirmation=allow_caption_confirmation,
            )
        if response is not None:
            return response

        pending_amount = _pending_direction_amount(
            extraction,
            processing_time.date(),
            force_confirmation=direction_conflict,
        )
        if pending_amount is not None:
            create_pending_receipt(
                db,
                user_id=user.id,
                whatsapp_message_id=whatsapp_message_id,
                extraction=extraction,
                current_time=processing_time,
            )
            return receipt_direction_confirmation(pending_amount)

        return receipt_not_registered_response(
            document_type=extraction.document_type,
            status=extraction.status,
        )


def _register_validated_receipt(
    db: Session,
    *,
    user: User,
    whatsapp_message_id: str,
    extraction: ReceiptExtraction,
    current_date: date,
    direction_override: ReceiptDirection | None = None,
    allow_direction_confirmation: bool = False,
) -> str | None:
    validated = _validate_receipt_for_registration(
        extraction,
        current_date=current_date,
        direction_override=direction_override,
        allow_direction_confirmation=allow_direction_confirmation,
    )
    if validated is None:
        return None

    transaction_type = (
        "expense" if validated.direction == "outflow" else "income"
    )
    category = find_category_or_default(
        db,
        user_id=user.id,
        category_name=extraction.category_suggestion,
        transaction_type=transaction_type,
    )
    description, counterparty = _receipt_description_and_counterparty(
        extraction,
        transaction_type=transaction_type,
    )

    try:
        transaction = create_transaction(
            db,
            user_id=user.id,
            type=transaction_type,
            amount=validated.amount,
            description=description,
            category_id=category.id,
            transaction_date=validated.transaction_date,
            payment_method=_receipt_payment_method(extraction.document_type),
            source="whatsapp_image",
            whatsapp_message_id=whatsapp_message_id,
        )
    except DuplicateWhatsAppMessageError:
        return None

    return receipt_transaction_confirmation(
        transaction_type=transaction_type,
        amount=transaction.amount,
        description=transaction.description,
        category=category.name,
        transaction_date=transaction.transaction_date,
        current_date=current_date,
        counterparty=counterparty,
    )


def _validate_receipt_for_registration(
    extraction: ReceiptExtraction,
    *,
    current_date: date,
    direction_override: ReceiptDirection | None = None,
    allow_direction_confirmation: bool = False,
) -> ValidatedReceipt | None:
    if extraction.document_type not in SUPPORTED_RECEIPT_DOCUMENTS:
        return None
    if extraction.status != "completed":
        return None
    if (extraction.currency or "").upper() != "BRL":
        return None
    if extraction.confidence < AUTO_REGISTER_CONFIDENCE:
        return None

    direction = direction_override or extraction.direction
    if direction not in {"outflow", "inflow"}:
        return None
    if extraction.requires_confirmation and not allow_direction_confirmation:
        return None
    amount = _parse_decimal_amount(extraction.amount)
    transaction_date = _parse_receipt_date(
        extraction.transaction_date,
        current_date=current_date,
    )
    if amount is None or transaction_date is None:
        return None

    return ValidatedReceipt(
        amount=amount,
        transaction_date=transaction_date,
        direction=direction,
    )


def _pending_direction_amount(
    extraction: ReceiptExtraction,
    current_date: date,
    *,
    force_confirmation: bool = False,
) -> Decimal | None:
    if extraction.direction != "unknown" and not force_confirmation:
        return None
    validated = _validate_receipt_for_registration(
        extraction,
        current_date=current_date,
        direction_override="outflow",
        allow_direction_confirmation=True,
    )
    return validated.amount if validated is not None else None


def _direction_from_caption(caption: str | None) -> ReceiptDirection:
    normalized = _normalize_text(caption or "")
    if (
        normalized in {"paguei", "eu paguei", "foi gasto", "pix enviado"}
        or normalized.startswith("paguei ")
        or " eu paguei " in f" {normalized} "
        or "pix enviado" in normalized
    ):
        return "outflow"
    if (
        normalized in {"recebi", "eu recebi", "foi entrada", "pix recebido"}
        or normalized.startswith("recebi ")
        or " eu recebi " in f" {normalized} "
        or "pix recebido" in normalized
    ):
        return "inflow"
    return "unknown"


def _parse_decimal_amount(value: str | None) -> Decimal | None:
    normalized = (value or "").strip().replace(",", ".")
    if not re.fullmatch(r"\d{1,12}(?:\.\d{1,2})?", normalized):
        return None
    try:
        amount = Decimal(normalized).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    return amount


def _parse_receipt_date(value: str | None, *, current_date: date) -> date | None:
    if value is None:
        return current_date
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed <= current_date else None


def _receipt_description_and_counterparty(
    extraction: ReceiptExtraction,
    *,
    transaction_type: str,
) -> tuple[str, str | None]:
    counterparty = (
        extraction.recipient_name
        if transaction_type == "expense"
        else extraction.payer_name
    )
    safe_counterparty = _safe_receipt_text(counterparty, max_length=80)
    description = _safe_receipt_text(extraction.description, max_length=255)
    if description:
        return description, safe_counterparty

    if transaction_type == "expense":
        fallback = f"PIX para {safe_counterparty}" if safe_counterparty else "PIX"
    else:
        fallback = (
            f"PIX recebido de {safe_counterparty}"
            if safe_counterparty
            else "PIX recebido"
        )
    return fallback, safe_counterparty


def _safe_receipt_text(value: str | None, *, max_length: int) -> str | None:
    normalized = " ".join((value or "").split())
    normalized = re.sub(r"\d{5,}", "", normalized)
    normalized = " ".join(normalized.split()).strip(" -–—:;")
    return normalized[:max_length] or None


def _receipt_payment_method(document_type: str) -> str | None:
    if document_type == "pix_receipt":
        return "PIX"
    if document_type == "bank_transfer_receipt":
        return "Transferência"
    return None


def _classify_pending_reply(text: str) -> tuple[str | None, Decimal | None]:
    normalized = _normalize_text(text)
    if normalized in {"paguei", "foi gasto", "saida", "eu paguei"}:
        return "outflow", None
    if normalized in {"recebi", "foi entrada", "entrou", "me pagaram"}:
        return "inflow", None
    if normalized in {"nao", "ignora", "deixa", "deixa pra la"}:
        return "discard", None

    correction_markers = ("na verdade", "era", "valor", "corrige")
    if any(marker in normalized for marker in correction_markers):
        match = re.search(r"\d{1,12}(?:[.,]\d{1,2})?", text)
        if match:
            amount = _parse_decimal_amount(match.group(0))
            if amount is not None:
                return "amount", amount
    return None, None


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


def _image_message_already_handled(whatsapp_message_id: str) -> bool:
    if engine is None:
        return False
    with SessionLocal() as db:
        return (
            get_transaction_by_whatsapp_message_id(db, whatsapp_message_id)
            is not None
            or get_pending_receipt_by_message_id(db, whatsapp_message_id)
            is not None
        )


def _get_user_name(whatsapp_phone: str) -> str | None:
    if engine is None:
        raise RuntimeError("Banco de dados indisponível")
    with SessionLocal() as db:
        return get_or_create_whatsapp_user(db, whatsapp_phone).name
