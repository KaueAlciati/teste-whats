from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.financial_transaction import FinancialTransaction


TRANSACTION_TYPES = {"expense", "income"}
TRANSACTION_SOURCES = {
    "whatsapp_text",
    "whatsapp_audio",
    "whatsapp_image",
    "whatsapp_document",
    "web",
}


class DuplicateWhatsAppMessageError(ValueError):
    pass


def _normalize_amount(amount: Decimal | str | int) -> Decimal:
    try:
        normalized_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("Valor monetário inválido") from exc

    if normalized_amount <= 0:
        raise ValueError("O valor deve ser maior que zero")
    return normalized_amount


def create_transaction(
    db: Session,
    *,
    user_id: int,
    type: str,
    amount: Decimal | str | int,
    description: str,
    transaction_date: date,
    source: str,
    category_id: int | None = None,
    payment_method: str | None = None,
    whatsapp_message_id: str | None = None,
    notes: str | None = None,
) -> FinancialTransaction:
    if type not in TRANSACTION_TYPES:
        raise ValueError("Tipo de movimentação inválido")
    if source not in TRANSACTION_SOURCES:
        raise ValueError("Origem da movimentação inválida")

    if whatsapp_message_id:
        existing_transaction = db.scalar(
            select(FinancialTransaction).where(
                FinancialTransaction.whatsapp_message_id == whatsapp_message_id
            )
        )
        if existing_transaction is not None:
            raise DuplicateWhatsAppMessageError(
                "Mensagem do WhatsApp já processada"
            )

    transaction = FinancialTransaction(
        user_id=user_id,
        type=type,
        amount=_normalize_amount(amount),
        description=description,
        category_id=category_id,
        transaction_date=transaction_date,
        payment_method=payment_method,
        source=source,
        whatsapp_message_id=whatsapp_message_id,
        notes=notes,
    )
    db.add(transaction)

    try:
        db.commit()
        db.refresh(transaction)
        return transaction
    except IntegrityError as exc:
        db.rollback()
        if whatsapp_message_id:
            raise DuplicateWhatsAppMessageError(
                "Mensagem do WhatsApp já processada"
            ) from exc
        raise


def get_transaction(
    db: Session,
    transaction_id: int,
    *,
    user_id: int | None = None,
) -> FinancialTransaction | None:
    statement = select(FinancialTransaction).where(
        FinancialTransaction.id == transaction_id
    )
    if user_id is not None:
        statement = statement.where(FinancialTransaction.user_id == user_id)
    return db.scalar(statement)


def get_transaction_by_whatsapp_message_id(
    db: Session,
    whatsapp_message_id: str,
) -> FinancialTransaction | None:
    return db.scalar(
        select(FinancialTransaction).where(
            FinancialTransaction.whatsapp_message_id == whatsapp_message_id
        )
    )


def list_transactions(
    db: Session,
    *,
    user_id: int,
    offset: int = 0,
    limit: int = 100,
) -> list[FinancialTransaction]:
    statement = (
        select(FinancialTransaction)
        .where(FinancialTransaction.user_id == user_id)
        .order_by(
            FinancialTransaction.transaction_date.desc(),
            FinancialTransaction.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


def calculate_balance(db: Session, *, user_id: int) -> Decimal:
    signed_amount = case(
        (FinancialTransaction.type == "income", FinancialTransaction.amount),
        else_=-FinancialTransaction.amount,
    )
    balance = db.scalar(
        select(func.coalesce(func.sum(signed_amount), 0)).where(
            FinancialTransaction.user_id == user_id
        )
    )
    return Decimal(str(balance)).quantize(Decimal("0.01"))


def has_transactions(db: Session, *, user_id: int) -> bool:
    transaction_id = db.scalar(
        select(FinancialTransaction.id)
        .where(FinancialTransaction.user_id == user_id)
        .limit(1)
    )
    return transaction_id is not None


def calculate_total_by_type(
    db: Session,
    *,
    user_id: int,
    transaction_type: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Decimal:
    if transaction_type not in TRANSACTION_TYPES:
        raise ValueError("Tipo de movimentação inválido")

    statement = select(
        func.coalesce(func.sum(FinancialTransaction.amount), 0)
    ).where(
        FinancialTransaction.user_id == user_id,
        FinancialTransaction.type == transaction_type,
    )
    if start_date is not None:
        statement = statement.where(
            FinancialTransaction.transaction_date >= start_date
        )
    if end_date is not None:
        statement = statement.where(
            FinancialTransaction.transaction_date <= end_date
        )

    total = db.scalar(statement)
    return Decimal(str(total)).quantize(Decimal("0.01"))
