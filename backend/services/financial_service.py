from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.category import Category
from backend.models.financial_transaction import FinancialTransaction


TRANSACTION_TYPES = {"expense", "income"}
TRANSACTION_SOURCES = {
    "whatsapp_text",
    "whatsapp_audio",
    "whatsapp_image",
    "whatsapp_document",
    "web",
    "dashboard_manual",
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


def get_latest_transaction_for_user(
    db: Session,
    *,
    user_id: int,
    created_after: datetime | None = None,
) -> FinancialTransaction | None:
    statement = (
        select(FinancialTransaction)
        .where(FinancialTransaction.user_id == user_id)
        .order_by(
            FinancialTransaction.created_at.desc(),
            FinancialTransaction.id.desc(),
        )
        .limit(1)
    )
    if created_after is not None:
        statement = statement.where(
            FinancialTransaction.created_at >= created_after
        )
    return db.scalar(statement)


def update_transaction(
    db: Session,
    *,
    transaction: FinancialTransaction,
    user_id: int,
    amount: Decimal | str | int | None = None,
    description: str | None = None,
    category: Category | None = None,
    transaction_date: date | None = None,
    payment_method: str | None = None,
    type: str | None = None,
) -> FinancialTransaction:
    if transaction.user_id != user_id:
        raise PermissionError("Movimentação pertence a outro usuário")

    final_type = type or transaction.type
    if final_type not in TRANSACTION_TYPES:
        raise ValueError("Tipo de movimentação inválido")

    if category is not None:
        if category.type != final_type:
            raise ValueError("Categoria incompatível com a movimentação")
        if category.user_id not in (None, user_id):
            raise PermissionError("Categoria pertence a outro usuário")
    elif type is not None and transaction.category is not None:
        if transaction.category.type != final_type:
            raise ValueError("Categoria incompatível com o novo tipo")

    normalized_amount = _normalize_amount(amount) if amount is not None else None
    normalized_description = None
    if description is not None:
        normalized_description = description.strip()
        if not normalized_description or len(normalized_description) > 255:
            raise ValueError("Descrição inválida")

    normalized_payment_method = None
    if payment_method is not None:
        normalized_payment_method = payment_method.strip()
        if not normalized_payment_method or len(normalized_payment_method) > 50:
            raise ValueError("Forma de pagamento inválida")

    if transaction_date is not None and (
        not isinstance(transaction_date, date)
        or isinstance(transaction_date, datetime)
    ):
        raise ValueError("Data da movimentação inválida")

    try:
        if normalized_amount is not None:
            transaction.amount = normalized_amount
        if normalized_description is not None:
            transaction.description = normalized_description
        if transaction_date is not None:
            transaction.transaction_date = transaction_date
        if normalized_payment_method is not None:
            transaction.payment_method = normalized_payment_method
        if type is not None:
            transaction.type = final_type
        if category is not None:
            transaction.category_id = category.id
            transaction.category = category

        db.commit()
        db.refresh(transaction)
        return transaction
    except SQLAlchemyError:
        db.rollback()
        raise


def delete_transaction(
    db: Session,
    *,
    transaction: FinancialTransaction,
    user_id: int,
) -> None:
    if transaction.user_id != user_id:
        raise PermissionError("Movimentação pertence a outro usuário")

    try:
        db.delete(transaction)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


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
