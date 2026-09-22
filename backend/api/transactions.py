from datetime import date, datetime
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.api.auth import get_current_user
from backend.database.connection import get_db
from backend.models.financial_transaction import FinancialTransaction
from backend.models.user import User
from backend.schemas.statement_import import (
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportPreviewRequest,
    ImportPreviewResponse,
)
from backend.schemas.transaction import TransactionResponse, TransactionWrite
from backend.services.category_service import get_or_create_user_category
from backend.services.attachment_service import (
    AttachmentStorageError,
    get_transaction_attachment,
    read_attachment_file,
)
from backend.services.financial_service import (
    create_transaction,
    delete_transaction,
    get_transaction,
    list_transactions,
    update_transaction,
)
from backend.services.statement_export_service import (
    custom_period,
    current_month_period,
    generate_statement,
)
from backend.services.statement_import_service import (
    StatementImportError,
    confirm_statement_import,
    preview_statement_import,
)


router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionResponse])
def get_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransactionResponse]:
    return [
        _transaction_response(transaction)
        for transaction in list_transactions(
            db,
            user_id=current_user.id,
            limit=1000,
        )
    ]


@router.get("/export")
def export_transactions(
    export_format: Literal["xlsx", "csv"] = Query("xlsx", alias="format"),
    start_date: date | None = None,
    end_date: date | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Informe data inicial e final para exportar um intervalo",
        )

    try:
        period = (
            custom_period(start_date, end_date)
            if start_date is not None and end_date is not None
            else current_month_period(
                datetime.now(ZoneInfo("America/Sao_Paulo")).date()
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None

    exported = generate_statement(
        db,
        user_id=current_user.id,
        period=period,
        export_format=export_format,
    )
    if exported is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhuma transação encontrada no período",
        )

    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{exported.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/import/preview", response_model=ImportPreviewResponse)
def preview_import(
    payload: ImportPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportPreviewResponse:
    try:
        return preview_statement_import(
            db,
            user_id=current_user.id,
            filename=payload.filename,
            content=payload.content,
            content_base64=payload.content_base64,
            mime_type=payload.mime_type,
            mapping=payload.mapping,
        )
    except StatementImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None


@router.post("/import/confirm", response_model=ImportConfirmResponse)
def confirm_import(
    payload: ImportConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportConfirmResponse:
    try:
        imported, skipped_duplicates = confirm_statement_import(
            db,
            user_id=current_user.id,
            rows=payload.rows,
            source_format=payload.source,
            attachment=payload.attachment,
        )
        return ImportConfirmResponse(
            imported=imported,
            skipped_duplicates=skipped_duplicates,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None
    except AttachmentStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from None


@router.get("/{transaction_id}/attachment")
def view_transaction_attachment(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    attachment = get_transaction_attachment(
        db,
        user_id=current_user.id,
        transaction_id=transaction_id,
    )
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comprovante não encontrado",
        )
    try:
        content = read_attachment_file(attachment)
    except AttachmentStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from None

    encoded_filename = quote(attachment.original_filename, safe="")
    return Response(
        content=content,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": (
                f"inline; filename*=UTF-8''{encoded_filename}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_transaction(
    payload: TransactionWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionResponse:
    try:
        category = get_or_create_user_category(
            db,
            user_id=current_user.id,
            category_name=payload.category,
            transaction_type=payload.type,
        )
        transaction = create_transaction(
            db,
            user_id=current_user.id,
            type=payload.type,
            amount=payload.amount,
            description=payload.description,
            category_id=category.id,
            transaction_date=payload.date,
            source="dashboard_manual",
        )
        return _transaction_response(transaction)
    except (LookupError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None


@router.put("/{transaction_id}", response_model=TransactionResponse)
def put_transaction(
    transaction_id: int,
    payload: TransactionWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionResponse:
    transaction = _owned_transaction(db, transaction_id, current_user.id)
    try:
        category = get_or_create_user_category(
            db,
            user_id=current_user.id,
            category_name=payload.category,
            transaction_type=payload.type,
        )
        updated = update_transaction(
            db,
            transaction=transaction,
            user_id=current_user.id,
            amount=payload.amount,
            description=payload.description,
            category=category,
            transaction_date=payload.date,
            type=payload.type,
        )
        return _transaction_response(updated)
    except (LookupError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from None


@router.delete("/{transaction_id}")
def remove_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    transaction = _owned_transaction(db, transaction_id, current_user.id)
    delete_transaction(
        db,
        transaction=transaction,
        user_id=current_user.id,
    )
    return {"status": "ok"}


def _owned_transaction(
    db: Session,
    transaction_id: int,
    user_id: int,
) -> FinancialTransaction:
    transaction = get_transaction(db, transaction_id, user_id=user_id)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transação não encontrada",
        )
    return transaction


def _transaction_response(
    transaction: FinancialTransaction,
) -> TransactionResponse:
    return TransactionResponse(
        id=transaction.id,
        description=transaction.description,
        amount=float(transaction.amount),
        type=transaction.type,
        category=(
            transaction.category.name
            if transaction.category is not None
            else "Sem categoria"
        ),
        date=transaction.transaction_date,
        source=transaction.source,
        has_attachment=bool(transaction.attachments),
    )
