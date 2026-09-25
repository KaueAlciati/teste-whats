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
from backend.schemas.statement_import import StatementDocumentExtraction
from backend.services.attachment_service import (
    AttachmentStorageError,
    StoredAttachment,
    delete_stored_file,
    link_attachment_to_transactions,
    promote_staged_attachment,
    stage_attachment_file,
    validate_attachment,
)
from backend.services.category_service import (
    find_existing_category,
    find_matching_existing_category,
    get_or_create_user_category,
)
from backend.services.conversation_service import (
    image_error_response,
    image_processing_response,
    image_too_large_response,
    image_unsupported_response,
    pending_receipt_discarded_response,
    pending_receipt_expired_response,
    pending_receipt_updated_response,
    receipt_direction_confirmation,
    receipt_identification_confirmation,
    receipt_not_registered_response,
    receipt_transaction_confirmation,
    response_variant,
)
from backend.services.financial_service import (
    DuplicateWhatsAppMessageError,
    create_transaction,
    get_transaction_by_whatsapp_message_id,
)
from backend.services.pending_receipt_service import (
    create_pending_receipt,
    delete_pending_receipt,
    get_pending_receipt_attachment,
    get_latest_pending_receipt_for_user,
    get_pending_receipt_by_message_id,
    get_pending_receipt_source,
    pending_receipt_is_expired,
    receipt_extraction_from_pending,
    update_pending_receipt_fields,
)
from backend.services.natural_period_service import resolve_natural_period
from backend.services.statement_document_service import (
    StatementDocumentError,
    extract_statement_document,
)
from backend.services.user_service import authorize_registered_whatsapp_user
from backend.services.whatsapp_media_service import (
    WhatsAppMediaError,
    WhatsAppMediaTooLargeError,
    WhatsAppMediaUnsupportedTypeError,
    download_whatsapp_media,
)
from backend.services.whatsapp_service import send_text_message


logger = logging.getLogger("uvicorn.error")

AUTO_REGISTER_CONFIDENCE = 0.65
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
    await _process_financial_receipt_media(
        whatsapp_phone,
        whatsapp_message_id,
        media_id,
        mime_type,
        caption,
        media_kind="image",
        transaction_source="whatsapp_image",
        filename=None,
    )


async def process_financial_document_message(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    media_id: str,
    mime_type: str | None,
    filename: str | None,
    caption: str | None,
) -> None:
    await _process_financial_receipt_media(
        whatsapp_phone,
        whatsapp_message_id,
        media_id,
        mime_type,
        caption,
        media_kind="document",
        transaction_source="whatsapp_document",
        filename=filename,
    )


async def _process_financial_receipt_media(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    media_id: str,
    mime_type: str | None,
    caption: str | None,
    *,
    media_kind: str,
    transaction_source: str,
    filename: str | None,
) -> None:
    staged_attachment: StoredAttachment | None = None
    try:
        user_id = await asyncio.to_thread(
            _get_authorized_user_id,
            whatsapp_phone,
        )
    except (SQLAlchemyError, RuntimeError, ValueError) as exc:
        logger.error(
            "Falha ao validar usuário do comprovante: tipo=%s",
            type(exc).__name__,
        )
        return
    if user_id is None:
        return

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
            fallback_filename=filename,
            media_kind=media_kind,
        )
        logger.info(
            "Download do comprovante concluído: mime_type=%s bytes=%s",
            media.mime_type,
            len(media.content),
        )
        processing_time = datetime.now(ZoneInfo("America/Sao_Paulo"))
        document_extraction = await asyncio.to_thread(
            extract_statement_document,
            media.content,
            mime_type=media.mime_type,
            filename=media.filename,
        )
        extraction = _receipt_from_statement_extraction(document_extraction)
        if extraction is None:
            response = receipt_not_registered_response(
                document_type="unknown",
                status="unknown",
            )
            await send_text_message(whatsapp_phone, response)
            return
        if _validate_receipt_for_confirmation(
            extraction,
            current_date=processing_time.date(),
        ) is None:
            response = receipt_not_registered_response(
                document_type=extraction.document_type,
                status=extraction.status,
            )
            await send_text_message(whatsapp_phone, response)
            return
        validated_attachment = validate_attachment(
            media.content,
            filename=media.filename,
            mime_type=media.mime_type,
        )
        staged_attachment = await asyncio.to_thread(
            stage_attachment_file,
            validated_attachment,
            user_id=user_id,
        )
        response = await asyncio.to_thread(
            _process_receipt_extraction,
            whatsapp_phone,
            whatsapp_message_id,
            extraction,
            processing_time,
            caption,
            staged_attachment,
            transaction_source,
        )
        if response is None and staged_attachment is not None:
            delete_stored_file(staged_attachment.storage_key)
    except WhatsAppMediaTooLargeError:
        logger.error("Imagem do WhatsApp excedeu o tamanho máximo")
        response = image_too_large_response()
    except WhatsAppMediaUnsupportedTypeError:
        logger.error("Imagem do WhatsApp possui formato não suportado")
        response = image_unsupported_response()
    except (WhatsAppMediaError, StatementDocumentError, AttachmentStorageError) as exc:
        if staged_attachment is not None:
            delete_stored_file(staged_attachment.storage_key)
        logger.error("Falha ao processar comprovante: tipo=%s", type(exc).__name__)
        response = image_error_response()
    except (SQLAlchemyError, RuntimeError, ValueError, LookupError) as exc:
        if staged_attachment is not None:
            delete_stored_file(staged_attachment.storage_key)
        logger.error(
            "Falha ao registrar análise de imagem: tipo=%s",
            type(exc).__name__,
        )
        response = image_error_response()
    except Exception as exc:
        if staged_attachment is not None:
            delete_stored_file(staged_attachment.storage_key)
        logger.exception(
            "Falha inesperada ao processar comprovante: tipo=%s",
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
    pending = get_latest_pending_receipt_for_user(db, user_id=user.id)
    if pending is None:
        return PendingReplyResult(handled=False)

    if pending_receipt_is_expired(pending, current_time=current_time):
        delete_pending_receipt(db, pending=pending, user_id=user.id)
        return PendingReplyResult(
            handled=True,
            response=pending_receipt_expired_response(),
        )

    extraction = receipt_extraction_from_pending(pending)
    changes, correction_error = _pending_receipt_correction(
        db,
        user_id=user.id,
        text=text,
        current_date=current_date,
        extraction=extraction,
    )
    if correction_error is not None:
        return PendingReplyResult(handled=True, response=correction_error)
    if changes:
        update_pending_receipt_fields(
            db,
            pending=pending,
            user_id=user.id,
            changes=changes,
        )
        extraction = receipt_extraction_from_pending(pending)
        validated = _validate_receipt_for_confirmation(
            extraction,
            current_date=current_date,
        )
        if validated is None:
            return PendingReplyResult(
                handled=True,
                response="Não consegui aplicar essa correção. Pode informar novamente?",
            )
        transaction_type = (
            "income" if extraction.direction == "inflow" else "expense"
        )
        description, _ = _receipt_description_and_counterparty(
            extraction,
            transaction_type=transaction_type,
        )
        return PendingReplyResult(
            handled=True,
            response=pending_receipt_updated_response(
                amount=validated.amount,
                description=description,
                transaction_date=validated.transaction_date,
                direction=extraction.direction,
                category=extraction.category_suggestion or "Sem categoria",
            ),
        )

    reply_type, _ = _classify_pending_reply(text)
    if reply_type is None:
        return PendingReplyResult(handled=False)

    if reply_type == "discard":
        delete_pending_receipt(db, pending=pending, user_id=user.id)
        return PendingReplyResult(
            handled=True,
            response=pending_receipt_discarded_response(),
        )

    if reply_type == "confirm" and extraction.direction == "unknown":
        amount = _parse_decimal_amount(extraction.amount)
        if amount is None:
            return PendingReplyResult(
                handled=True,
                response=receipt_not_registered_response(
                    document_type=extraction.document_type,
                    status=extraction.status,
                ),
            )
        return PendingReplyResult(
            handled=True,
            response=receipt_direction_confirmation(amount),
        )
    direction: ReceiptDirection = extraction.direction
    if reply_type == "outflow":
        direction = "outflow"
    elif reply_type == "inflow":
        direction = "inflow"
    response = _register_validated_receipt(
        db,
        user=user,
        pending=pending,
        whatsapp_message_id=pending.whatsapp_message_id,
        extraction=extraction,
        current_date=current_date,
        direction_override=direction,
        allow_direction_confirmation=True,
    )
    if response is None:
        delete_pending_receipt(db, pending=pending, user_id=user.id)
        response = receipt_not_registered_response(
            document_type=extraction.document_type,
            status=extraction.status,
        )
    return PendingReplyResult(handled=True, response=response)


def _process_receipt_extraction(
    whatsapp_phone: str,
    whatsapp_message_id: str,
    extraction: ReceiptExtraction,
    processing_time: datetime,
    caption: str | None = None,
    attachment: StoredAttachment | None = None,
    transaction_source: str = "whatsapp_image",
) -> str | None:
    if engine is None:
        if attachment is not None:
            delete_stored_file(attachment.storage_key)
        raise RuntimeError("Banco de dados indisponível")

    with SessionLocal() as db:
        user = authorize_registered_whatsapp_user(db, whatsapp_phone)
        if user is None:
            if attachment is not None:
                delete_stored_file(attachment.storage_key)
            return None
        if (
            get_transaction_by_whatsapp_message_id(db, whatsapp_message_id)
            is not None
        ):
            if attachment is not None:
                delete_stored_file(attachment.storage_key)
            return None
        if get_pending_receipt_by_message_id(db, whatsapp_message_id) is not None:
            if attachment is not None:
                delete_stored_file(attachment.storage_key)
            return None

        caption_direction = _direction_from_caption(caption)
        direction_override: ReceiptDirection | None = None
        direction_conflict = False
        if caption_direction in {"outflow", "inflow"}:
            if extraction.direction == "unknown":
                direction_override = caption_direction
            elif extraction.direction != caption_direction:
                direction_conflict = True

        if direction_conflict:
            extraction = extraction.model_copy(update={"direction": "unknown"})
        elif direction_override is not None:
            extraction = extraction.model_copy(update={"direction": direction_override})

        if _validate_receipt_for_confirmation(
            extraction,
            current_date=processing_time.date(),
        ) is None:
            if attachment is not None:
                delete_stored_file(attachment.storage_key)
            return receipt_not_registered_response(
                document_type=extraction.document_type,
                status=extraction.status,
            )

        create_pending_receipt(
            db,
            user_id=user.id,
            whatsapp_message_id=whatsapp_message_id,
            extraction=extraction,
            current_time=processing_time,
            attachment=attachment,
            transaction_source=transaction_source,
        )
        validated = _validate_receipt_for_confirmation(
            extraction,
            current_date=processing_time.date(),
        )
        assert validated is not None
        description, _ = _receipt_description_and_counterparty(
            extraction,
            transaction_type=(
                "income" if extraction.direction == "inflow" else "expense"
            ),
        )
        return receipt_identification_confirmation(
            direction=extraction.direction,
            amount=validated.amount,
            description=description,
            transaction_date=validated.transaction_date,
            current_date=processing_time.date(),
        )


def _register_validated_receipt(
    db: Session,
    *,
    user: User,
    pending: PendingReceipt,
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
    category = None
    if extraction.category_suggestion:
        category = find_existing_category(
            db,
            user_id=user.id,
            category_name=extraction.category_suggestion,
            transaction_type=transaction_type,
        )
    description, counterparty = _receipt_description_and_counterparty(
        extraction,
        transaction_type=transaction_type,
    )

    staged_attachment = get_pending_receipt_attachment(pending)
    if staged_attachment is None:
        return None
    stored_attachment = promote_staged_attachment(
        staged_attachment,
        user_id=user.id,
    )
    try:
        transaction = create_transaction(
            db,
            user_id=user.id,
            type=transaction_type,
            amount=validated.amount,
            description=description,
            category_id=category.id if category is not None else None,
            transaction_date=validated.transaction_date,
            payment_method=_receipt_payment_method(extraction.document_type),
            source=get_pending_receipt_source(pending),
            whatsapp_message_id=whatsapp_message_id,
            commit=False,
        )
        link_attachment_to_transactions(
            db,
            user_id=user.id,
            transactions=[transaction],
            stored=stored_attachment,
        )
        db.delete(pending)
        db.commit()
    except DuplicateWhatsAppMessageError:
        db.rollback()
        delete_stored_file(stored_attachment.storage_key)
        return None
    except Exception:
        db.rollback()
        delete_stored_file(stored_attachment.storage_key)
        raise

    delete_stored_file(staged_attachment.storage_key)

    return receipt_transaction_confirmation(
        transaction_type=transaction_type,
        amount=transaction.amount,
        description=transaction.description,
        category=category.name if category is not None else "Sem categoria",
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
    validated = _validate_receipt_for_confirmation(
        extraction,
        current_date=current_date,
    )
    if validated is None:
        return None

    direction = direction_override or extraction.direction
    if direction not in {"outflow", "inflow"}:
        return None
    if extraction.requires_confirmation and not allow_direction_confirmation:
        return None
    return ValidatedReceipt(
        amount=validated.amount,
        transaction_date=validated.transaction_date,
        direction=direction,
    )


def _validate_receipt_for_confirmation(
    extraction: ReceiptExtraction,
    *,
    current_date: date,
) -> ValidatedReceipt | None:
    if extraction.document_type not in SUPPORTED_RECEIPT_DOCUMENTS:
        return None
    if extraction.status != "completed":
        return None
    if (extraction.currency or "").upper() != "BRL":
        return None
    if extraction.confidence < AUTO_REGISTER_CONFIDENCE:
        return None

    amount = _parse_decimal_amount(extraction.amount)
    transaction_date = _parse_receipt_date(
        extraction.transaction_date,
        current_date=current_date,
    )
    if amount is None or transaction_date is None:
        return None
    if not _safe_receipt_text(extraction.description, max_length=255):
        return None

    return ValidatedReceipt(
        amount=amount,
        transaction_date=transaction_date,
        direction=extraction.direction,
    )


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
        return None
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


def _pending_receipt_correction(
    db: Session,
    *,
    user_id: int,
    text: str,
    current_date: date,
    extraction: ReceiptExtraction,
) -> tuple[dict[str, object], str | None]:
    normalized = _normalize_text(text)
    changes: dict[str, object] = {}

    direction = _corrected_receipt_direction(normalized)
    if direction is not None:
        changes["direction"] = direction

    date_requested = bool(
        re.search(r"\bdata\b", normalized)
        or re.fullmatch(r"(?:foi\s+)?(?:hoje|ontem|anteontem)", normalized)
    )
    if date_requested:
        period = resolve_natural_period(text, current_date=current_date)
        if (
            not period.is_valid
            or period.start_date is None
            or period.start_date != period.end_date
            or period.start_date > current_date
        ):
            return {}, "Não consegui entender essa data. Pode informar novamente?"
        changes["transaction_date"] = period.start_date.isoformat()

    amount_match = _corrected_receipt_amount(text, normalized)
    if amount_match is not None:
        changes["amount"] = f"{amount_match:.2f}"

    description = _corrected_receipt_description(text)
    if description is not None:
        safe_description = _safe_receipt_text(description, max_length=255)
        if safe_description is None:
            return {}, "Qual descrição válida você quer usar no comprovante?"
        changes["description"] = safe_description

    category_requested, category_name = _corrected_receipt_category(text)
    if category_requested:
        if _normalize_text(category_name or "") in {
            "sem categoria",
            "nenhuma categoria",
        }:
            changes["category_suggestion"] = None
        else:
            requested_type = (
                "income"
                if changes.get("direction", extraction.direction) == "inflow"
                else "expense"
            )
            category = find_matching_existing_category(
                db,
                user_id=user_id,
                category_name=category_name or "",
                transaction_type=requested_type,
            )
            if category is None:
                category = get_or_create_user_category(
                    db,
                    user_id=user_id,
                    category_name=_category_display_name(category_name or ""),
                    transaction_type=requested_type,
                )
            changes["category_suggestion"] = category.name

    return changes, None


def _corrected_receipt_direction(normalized: str) -> ReceiptDirection | None:
    prefix = r"(?:isso|esse|comprovante|na verdade)\s+(?:e|foi)\s+"
    if normalized in {"entrada", "receita", "recebimento"} or re.search(
        rf"\b(?:{prefix}|tipo\s+)(?:uma\s+)?(?:entrada|receita|recebimento)\b",
        normalized,
    ):
        return "inflow"
    if normalized in {"saida", "despesa", "gasto"} or re.search(
        rf"\b(?:{prefix}|tipo\s+)(?:uma\s+)?(?:saida|despesa|gasto)\b",
        normalized,
    ):
        return "outflow"
    return None


def _corrected_receipt_amount(text: str, normalized: str) -> Decimal | None:
    if re.search(r"\b(?:data|dia)\b", normalized):
        return None
    patterns = (
        r"\b(?:o\s+)?valor\b[^0-9]{0,30}"
        r"(?:r\$\s*)?(\d{1,12}(?:[.,]\d{1,2})?)",
        r"\bera\s+(?:r\$\s*)?(\d{1,12}(?:[.,]\d{1,2})?)\s*reais?\b",
        r"\b(?:na\s+verdade|corrige(?:\s+o\s+valor)?(?:\s+para)?)\s+"
        r"(?:e|é)?\s*(?:r\$\s*)?(\d{1,12}(?:[.,]\d{1,2})?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is not None:
            return _parse_decimal_amount(match.group(1))
    return None


def _corrected_receipt_description(text: str) -> str | None:
    patterns = (
        r"\b(?:a\s+)?descri[cç][aã]o\s+(?:e|é|era|foi|para)?\s+(.+)$",
        r"\bcoloca\s+(.+?)\s+na\s+descri[cç][aã]o\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is not None:
            return _trim_receipt_correction_value(match.group(1))
    return None


def _corrected_receipt_category(text: str) -> tuple[bool, str | None]:
    patterns = (
        r"\bmuda\s+a\s+categoria\s+para\s+(.+)$",
        r"\bcoloca\s+na\s+categoria\s+(.+)$",
        r"\b(?:esse|isso)\s+e\s+da\s+categoria\s+(.+)$",
        r"\besse\s+comprovante\s+e\s+(.+)$",
        r"\bmarca\s+como\s+(.+)$",
        r"\bcria\s+categoria\s+(.+)$",
        r"\bcategoria\s+(?:e|é|era|para)?\s*(.+)$",
        r"\bcoloca\s+em\s+(.+)$",
    )
    normalized_text = unicodedata.normalize("NFKD", text)
    normalized_text = "".join(
        character
        for character in normalized_text
        if not unicodedata.combining(character)
    )
    for pattern in patterns:
        match = re.search(pattern, normalized_text, flags=re.IGNORECASE)
        if match is not None:
            return True, _trim_receipt_correction_value(match.group(1))
    return False, None


def _trim_receipt_correction_value(value: str) -> str:
    cleaned = re.split(
        r"\s+(?:no|do|o)\s+comprovante\b|\s+arrum[ae]\b|"
        r"\s+marque\b|\s+pra\s+(?:mim|esse\s+gasto)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return " ".join(cleaned.strip(" .,!?:;-").split())


def _category_display_name(value: str) -> str:
    return " ".join(value.strip().split()).title()


def _classify_pending_reply(text: str) -> tuple[str | None, Decimal | None]:
    normalized = _normalize_text(text)
    if normalized in {"sim", "isso", "isso mesmo", "correto", "confirmo"}:
        return "confirm", None
    if normalized in {"paguei", "foi gasto", "saida", "eu paguei"}:
        return "outflow", None
    if normalized in {"recebi", "foi entrada", "entrou", "me pagaram"}:
        return "inflow", None
    if normalized in {"nao", "ignora", "deixa", "deixa pra la"}:
        return "discard", None

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


def _get_authorized_user_id(whatsapp_phone: str) -> int | None:
    if engine is None:
        raise RuntimeError("Banco de dados indisponível")
    with SessionLocal() as db:
        user = authorize_registered_whatsapp_user(db, whatsapp_phone)
        return user.id if user is not None else None


def _receipt_from_statement_extraction(
    extraction: StatementDocumentExtraction,
) -> ReceiptExtraction | None:
    if extraction.document_type != "single_receipt":
        return None
    if len(extraction.movements) != 1:
        return None
    movement = extraction.movements[0]
    return ReceiptExtraction(
        document_type="payment_receipt",
        amount=movement.amount,
        currency="BRL" if movement.amount else None,
        transaction_date=movement.transaction_date,
        transaction_time=None,
        payer_name=None,
        payer_institution=None,
        recipient_name=None,
        recipient_institution=None,
        pix_key=None,
        end_to_end_id=None,
        description=movement.description,
        direction=movement.direction,
        category_suggestion=None,
        status="completed",
        confidence=movement.confidence,
        requires_confirmation=True,
        reason=movement.reason,
    )
