import base64
import binascii
import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.financial_transaction import FinancialTransaction
from backend.schemas.statement_import import (
    ImportColumnMapping,
    ImportConfirmRow,
    ImportPreviewResponse,
    ImportPreviewRow,
    StatementDocumentExtraction,
    StatementExtractedMovement,
)
from backend.services.category_service import get_or_create_user_category
from backend.services.financial_service import create_transaction
from backend.services.statement_document_service import (
    StatementDocumentError,
    extract_statement_document,
)


MAX_CSV_ROWS = 5000
MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024
IMPORT_SOURCE_BY_FORMAT = {
    "csv": "import_csv",
    "pdf": "import_pdf",
    "image": "import_image",
}


class StatementImportError(ValueError):
    pass


HEADER_ALIASES = {
    "date_column": {
        "data",
        "date",
        "data lancamento",
        "data do lancamento",
        "data movimento",
        "data da movimentacao",
        "dt lancamento",
    },
    "description_column": {
        "descricao",
        "description",
        "historico",
        "lancamento",
        "detalhes",
        "estabelecimento",
        "memo",
    },
    "amount_column": {
        "valor",
        "amount",
        "montante",
        "valor r$",
        "valor lancamento",
    },
    "type_column": {
        "tipo",
        "type",
        "natureza",
        "debito credito",
        "credito debito",
        "d c",
    },
    "credit_column": {"credito", "credit", "entrada", "receita"},
    "debit_column": {"debito", "debit", "saida", "despesa"},
}


CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Transporte", ("posto", "shell", "ipiranga", "uber", "taxi", "99", "metro", "onibus")),
    ("Alimentação", ("ifood", "rappi", "restaurante", "lanchonete", "padaria", "mercado", "supermercado")),
    ("Saúde", ("farmacia", "drogaria", "hospital", "clinica")),
    ("Moradia", ("aluguel", "condominio", "energia", "luz", "iptu")),
    ("Assinaturas", ("netflix", "spotify", "prime video", "disney", "hbo")),
    ("Lazer", ("cinema", "teatro", "ingresso", "show")),
    ("Salário", ("salario", "pro labore")),
)


@dataclass(frozen=True)
class ParsedCsv:
    delimiter: str
    columns: list[str]
    rows: list[dict[str, str]]


def preview_statement_import(
    db: Session,
    *,
    user_id: int,
    filename: str,
    content: str | None,
    content_base64: str | None,
    mime_type: str | None,
    mapping: ImportColumnMapping | None,
) -> ImportPreviewResponse:
    extension = _file_extension(filename)
    if extension == ".csv":
        if content is None or content_base64 is not None:
            raise StatementImportError("Conteúdo CSV inválido")
        return preview_csv_import(
            db,
            user_id=user_id,
            filename=filename,
            content=content,
            mapping=mapping,
        )

    if extension not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise StatementImportError(
            "Formato não suportado. Use CSV, PDF, JPG, JPEG ou PNG"
        )
    if mapping is not None:
        raise StatementImportError("Mapeamento manual é exclusivo para CSV")
    if content_base64 is None or content is not None:
        raise StatementImportError("Conteúdo binário inválido")

    file_bytes = _decode_binary_content(content_base64)
    detected_mime_type = _validate_binary_file(
        file_bytes,
        extension=extension,
        declared_mime_type=mime_type,
    )
    try:
        extraction = extract_statement_document(
            file_bytes,
            mime_type=detected_mime_type,
            filename=filename,
        )
    except StatementDocumentError as exc:
        raise StatementImportError(str(exc)) from exc

    if extraction.document_type not in {"bank_statement", "single_receipt"}:
        raise StatementImportError(
            extraction.reason
            or "Não foi possível reconhecer um extrato ou comprovante"
        )
    if not extraction.movements:
        raise StatementImportError(
            "Nenhuma movimentação legível foi encontrada no arquivo"
        )
    if (
        extraction.document_type == "single_receipt"
        and len(extraction.movements) != 1
    ):
        raise StatementImportError(
            "O comprovante individual deve conter uma única movimentação"
        )

    source = "pdf" if extension == ".pdf" else "image"
    rows = _normalize_extracted_movements(extraction)
    _mark_duplicate_rows(db, user_id=user_id, rows=rows)
    return _build_preview_response(
        filename=filename,
        source=source,
        rows=rows,
    )


def preview_csv_import(
    db: Session,
    *,
    user_id: int,
    filename: str,
    content: str,
    mapping: ImportColumnMapping | None,
) -> ImportPreviewResponse:
    if not filename.casefold().endswith(".csv"):
        raise StatementImportError("Envie um arquivo CSV")

    parsed = _read_csv(content)
    resolved_mapping = mapping or _detect_mapping(parsed.columns)
    mapping_required = not _mapping_is_complete(resolved_mapping)

    if mapping is not None:
        _validate_mapping(mapping, parsed.columns)
        mapping_required = False

    if mapping_required:
        return ImportPreviewResponse(
            filename=filename,
            source="csv",
            delimiter=parsed.delimiter,
            columns=parsed.columns,
            mapping_required=True,
            mapping=resolved_mapping,
            sample_rows=parsed.rows[:5],
            total=len(parsed.rows),
            ready=0,
            possible_duplicates=0,
            needs_review=0,
            invalid=0,
            rows=[],
        )

    assert resolved_mapping is not None
    _validate_mapping(resolved_mapping, parsed.columns)
    preview_rows: list[ImportPreviewRow] = []

    for index, raw_row in enumerate(parsed.rows, start=2):
        preview_row = _normalize_row(index, raw_row, resolved_mapping)
        preview_rows.append(preview_row)

    _mark_duplicate_rows(db, user_id=user_id, rows=preview_rows)

    return ImportPreviewResponse(
        filename=filename,
        source="csv",
        delimiter=parsed.delimiter,
        columns=parsed.columns,
        mapping_required=False,
        mapping=resolved_mapping,
        sample_rows=[],
        total=len(preview_rows),
        ready=sum(row.status == "ready" for row in preview_rows),
        possible_duplicates=sum(
            row.status == "possible_duplicate" for row in preview_rows
        ),
        needs_review=0,
        invalid=sum(row.status == "invalid" for row in preview_rows),
        rows=preview_rows,
    )


def confirm_statement_import(
    db: Session,
    *,
    user_id: int,
    rows: list[ImportConfirmRow],
    source_format: str,
) -> tuple[int, int]:
    transaction_source = IMPORT_SOURCE_BY_FORMAT.get(source_format)
    if transaction_source is None:
        raise StatementImportError("Origem de importação inválida")
    existing_fingerprints = _existing_fingerprints(db, user_id=user_id)
    imported_fingerprints: set[tuple[date, Decimal, str, str]] = set()
    imported = 0
    skipped_duplicates = 0

    for row in rows:
        fingerprint = transaction_fingerprint(
            transaction_date=row.date,
            amount=Decimal(str(row.amount)),
            description=row.description,
            transaction_type=row.type,
        )
        is_duplicate = (
            fingerprint in existing_fingerprints
            or fingerprint in imported_fingerprints
        )
        if is_duplicate and not row.allow_duplicate:
            skipped_duplicates += 1
            continue

        category_id = None
        if row.category:
            category = get_or_create_user_category(
                db,
                user_id=user_id,
                category_name=row.category,
                transaction_type=row.type,
            )
            category_id = category.id
        create_transaction(
            db,
            user_id=user_id,
            type=row.type,
            amount=Decimal(str(row.amount)),
            description=row.description,
            category_id=category_id,
            transaction_date=row.date,
            source=transaction_source,
        )
        imported_fingerprints.add(fingerprint)
        imported += 1

    return imported, skipped_duplicates


def confirm_csv_import(
    db: Session,
    *,
    user_id: int,
    rows: list[ImportConfirmRow],
) -> tuple[int, int]:
    return confirm_statement_import(
        db,
        user_id=user_id,
        rows=rows,
        source_format="csv",
    )


def _normalize_extracted_movements(
    extraction: StatementDocumentExtraction,
) -> list[ImportPreviewRow]:
    return [
        _normalize_extracted_movement(
            index,
            movement,
            suggest_category=extraction.document_type == "bank_statement",
        )
        for index, movement in enumerate(extraction.movements, start=1)
    ]


def _normalize_extracted_movement(
    row_id: int,
    movement: StatementExtractedMovement,
    *,
    suggest_category: bool,
) -> ImportPreviewRow:
    errors: list[str] = []
    description = " ".join((movement.description or "").split())
    transaction_date: date | None = None
    amount: Decimal | None = None
    transaction_type: str | None = None
    direction_needs_review = False

    if not description:
        errors.append("Descrição ilegível")
        description = "(movimentação sem descrição legível)"
    elif len(description) > 255:
        description = description[:255].rstrip()

    if movement.transaction_date:
        try:
            transaction_date = _parse_date(movement.transaction_date)
        except StatementImportError:
            errors.append("Data ilegível")
    else:
        errors.append("Data ausente")

    if movement.amount:
        try:
            amount = abs(_parse_amount(movement.amount)).quantize(
                Decimal("0.01")
            )
            if amount <= 0:
                errors.append("Valor inválido")
                amount = None
        except StatementImportError:
            errors.append("Valor ilegível")
    else:
        errors.append("Valor ausente")

    if movement.direction == "inflow":
        transaction_type = "income"
    elif movement.direction == "outflow":
        transaction_type = "expense"
    else:
        direction_needs_review = True

    if movement.confidence < 0.65:
        errors.append("Leitura com baixa confiança")
    if movement.reason and errors:
        errors.append(movement.reason[:160])

    category = None
    category_source = "none"
    if suggest_category and description and not description.startswith("("):
        category, category_source = _suggest_category(description)

    if errors:
        status = "invalid"
        if direction_needs_review:
            errors.insert(0, "Entrada/saída não identificada")
    elif direction_needs_review:
        status = "needs_review"
        errors.append("Escolha se a movimentação é entrada ou saída")
    else:
        status = "ready"

    return ImportPreviewRow(
        id=row_id,
        line_number=row_id,
        date=transaction_date,
        description=description,
        amount=float(amount) if amount is not None else None,
        type=transaction_type,
        category=category,
        category_source=category_source,
        status=status,
        error_reason="; ".join(dict.fromkeys(errors)) or None,
    )


def _mark_duplicate_rows(
    db: Session,
    *,
    user_id: int,
    rows: list[ImportPreviewRow],
) -> None:
    existing_fingerprints = _existing_fingerprints(db, user_id=user_id)
    seen_fingerprints: set[tuple[date, Decimal, str, str]] = set()
    for row in rows:
        if row.status in {"invalid", "needs_review"}:
            continue
        assert row.date is not None
        assert row.amount is not None
        assert row.type is not None
        fingerprint = transaction_fingerprint(
            transaction_date=row.date,
            amount=Decimal(str(row.amount)),
            description=row.description,
            transaction_type=row.type,
        )
        if fingerprint in existing_fingerprints or fingerprint in seen_fingerprints:
            row.status = "possible_duplicate"
        seen_fingerprints.add(fingerprint)


def _build_preview_response(
    *,
    filename: str,
    source: str,
    rows: list[ImportPreviewRow],
) -> ImportPreviewResponse:
    return ImportPreviewResponse(
        filename=filename,
        source=source,
        delimiter=None,
        columns=[],
        mapping_required=False,
        mapping=None,
        sample_rows=[],
        total=len(rows),
        ready=sum(row.status == "ready" for row in rows),
        possible_duplicates=sum(
            row.status == "possible_duplicate" for row in rows
        ),
        needs_review=sum(row.status == "needs_review" for row in rows),
        invalid=sum(row.status == "invalid" for row in rows),
        rows=rows,
    )


def _file_extension(filename: str) -> str:
    normalized = filename.casefold().strip()
    if "." not in normalized:
        return ""
    return "." + normalized.rsplit(".", 1)[1]


def _decode_binary_content(content_base64: str) -> bytes:
    try:
        file_bytes = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise StatementImportError("Conteúdo binário inválido") from exc
    if not file_bytes:
        raise StatementImportError("Arquivo vazio")
    if len(file_bytes) > MAX_IMPORT_FILE_SIZE:
        raise StatementImportError("O arquivo excede o limite de 10 MB")
    return file_bytes


def _validate_binary_file(
    file_bytes: bytes,
    *,
    extension: str,
    declared_mime_type: str | None,
) -> str:
    if extension == ".pdf":
        expected_mime_type = "application/pdf"
        valid_signature = file_bytes.startswith(b"%PDF-")
    elif extension in {".jpg", ".jpeg"}:
        expected_mime_type = "image/jpeg"
        valid_signature = file_bytes.startswith(b"\xff\xd8\xff")
    else:
        expected_mime_type = "image/png"
        valid_signature = file_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    if not valid_signature:
        raise StatementImportError("O conteúdo do arquivo não corresponde ao formato")
    normalized_declared = (declared_mime_type or "").casefold().strip()
    if normalized_declared and normalized_declared not in {
        expected_mime_type,
        "application/octet-stream",
    }:
        raise StatementImportError("Tipo do arquivo não corresponde à extensão")
    return expected_mime_type


def transaction_fingerprint(
    *,
    transaction_date: date,
    amount: Decimal,
    description: str,
    transaction_type: str,
) -> tuple[date, Decimal, str, str]:
    return (
        transaction_date,
        amount.quantize(Decimal("0.01")),
        _normalize_text(description),
        transaction_type,
    )


def _read_csv(content: str) -> ParsedCsv:
    clean_content = content.lstrip("\ufeff")
    if not clean_content.strip():
        raise StatementImportError("O arquivo CSV está vazio")

    sample = clean_content[:8192]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","

    try:
        reader = csv.DictReader(io.StringIO(clean_content), delimiter=delimiter)
        columns = [column.strip() for column in (reader.fieldnames or [])]
        if not columns or any(not column for column in columns):
            raise StatementImportError("O CSV precisa ter uma linha de cabeçalho")
        if len({_normalize_text(column) for column in columns}) != len(columns):
            raise StatementImportError("O CSV possui cabeçalhos repetidos")

        rows: list[dict[str, str]] = []
        for row in reader:
            normalized_row = {
                column: str(value or "").strip()
                for column, value in zip(columns, row.values(), strict=False)
            }
            if any(normalized_row.values()):
                rows.append(normalized_row)
            if len(rows) > MAX_CSV_ROWS:
                raise StatementImportError(
                    f"O CSV excede o limite de {MAX_CSV_ROWS} movimentações"
                )
    except csv.Error as exc:
        raise StatementImportError("Não foi possível interpretar o arquivo CSV") from exc

    if not rows:
        raise StatementImportError("O CSV não contém movimentações")
    return ParsedCsv(delimiter=delimiter, columns=columns, rows=rows)


def _detect_mapping(columns: list[str]) -> ImportColumnMapping | None:
    matches: dict[str, str | None] = {}
    normalized_columns = {column: _normalize_text(column) for column in columns}
    for role, aliases in HEADER_ALIASES.items():
        candidates = [
            column
            for column, normalized in normalized_columns.items()
            if normalized in {_normalize_text(alias) for alias in aliases}
        ]
        matches[role] = candidates[0] if len(candidates) == 1 else None

    if not matches["date_column"] or not matches["description_column"]:
        return None
    if not matches["amount_column"] and not (
        matches["credit_column"] or matches["debit_column"]
    ):
        return None
    return ImportColumnMapping(**matches)


def _mapping_is_complete(mapping: ImportColumnMapping | None) -> bool:
    return mapping is not None


def _validate_mapping(mapping: ImportColumnMapping, columns: list[str]) -> None:
    selected = [
        mapping.date_column,
        mapping.description_column,
        mapping.amount_column,
        mapping.type_column,
        mapping.credit_column,
        mapping.debit_column,
    ]
    missing = [column for column in selected if column and column not in columns]
    if missing:
        raise StatementImportError(
            "Coluna não encontrada no CSV: " + ", ".join(missing)
        )


def _normalize_row(
    row_id: int,
    raw_row: dict[str, str],
    mapping: ImportColumnMapping,
) -> ImportPreviewRow:
    description = raw_row.get(mapping.description_column, "").strip()
    try:
        transaction_date = _parse_date(raw_row.get(mapping.date_column, ""))
        if not description:
            raise StatementImportError("Descrição vazia")
        if len(description) > 255:
            raise StatementImportError("Descrição excede 255 caracteres")
        amount, transaction_type = _parse_amount_and_type(raw_row, mapping)
        category, category_source = _suggest_category(description)
        return ImportPreviewRow(
            id=row_id - 1,
            line_number=row_id,
            date=transaction_date,
            description=description,
            amount=float(amount),
            type=transaction_type,
            category=category,
            category_source=category_source,
            status="ready",
        )
    except (StatementImportError, InvalidOperation) as exc:
        return ImportPreviewRow(
            id=row_id - 1,
            line_number=row_id,
            date=None,
            description=description or "(linha sem descrição)",
            amount=None,
            type=None,
            category=None,
            category_source="none",
            status="invalid",
            error_reason=str(exc),
        )


def _parse_amount_and_type(
    raw_row: dict[str, str],
    mapping: ImportColumnMapping,
) -> tuple[Decimal, str]:
    credit_raw = raw_row.get(mapping.credit_column, "") if mapping.credit_column else ""
    debit_raw = raw_row.get(mapping.debit_column, "") if mapping.debit_column else ""

    if credit_raw.strip():
        amount = abs(_parse_amount(credit_raw))
        transaction_type = "income"
    elif debit_raw.strip():
        amount = abs(_parse_amount(debit_raw))
        transaction_type = "expense"
    elif mapping.amount_column:
        signed_amount = _parse_amount(raw_row.get(mapping.amount_column, ""))
        explicit_type = (
            _parse_transaction_type(raw_row.get(mapping.type_column, ""))
            if mapping.type_column
            else None
        )
        transaction_type = explicit_type or (
            "expense" if signed_amount < 0 else "income"
        )
        amount = abs(signed_amount)
    else:
        raise StatementImportError("Valor ausente")

    if amount <= 0:
        raise StatementImportError("O valor deve ser maior que zero")
    return amount.quantize(Decimal("0.01")), transaction_type


def _parse_amount(raw: str) -> Decimal:
    text = raw.strip()
    if not text:
        raise StatementImportError("Valor vazio")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("R$", "").replace(" ", "")
    if text.startswith("-"):
        negative = True
    text = text.lstrip("+-")
    text = re.sub(r"[^0-9,.]", "", text)
    if not text:
        raise StatementImportError("Valor inválido")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        whole, decimal_part = text.rsplit(",", 1)
        text = (
            whole.replace(",", "") + "." + decimal_part
            if len(decimal_part) in (1, 2)
            else text.replace(",", "")
        )
    elif text.count(".") > 1:
        parts = text.split(".")
        text = "".join(parts[:-1]) + "." + parts[-1]
    elif "." in text and len(text.rsplit(".", 1)[1]) == 3:
        text = text.replace(".", "")

    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise StatementImportError("Valor inválido") from exc
    return -value if negative else value


def _parse_transaction_type(raw: str) -> str | None:
    normalized = _normalize_text(raw)
    if not normalized:
        return None
    if normalized in {"credito", "credit", "c", "entrada", "income", "receita"}:
        return "income"
    if normalized in {"debito", "debit", "d", "saida", "expense", "despesa"}:
        return "expense"
    raise StatementImportError(f"Tipo de movimentação não reconhecido: {raw}")


def _parse_date(raw: str) -> date:
    text = raw.strip().split(" ", 1)[0]
    for date_format in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    raise StatementImportError(f"Data não reconhecida: {raw}")


def _suggest_category(description: str) -> tuple[str, str]:
    normalized = _normalize_text(description)
    for category, keywords in CATEGORY_RULES:
        if any(keyword in normalized for keyword in keywords):
            return category, "rule"
    return "Outros", "fallback"


def _existing_fingerprints(
    db: Session,
    *,
    user_id: int,
) -> set[tuple[date, Decimal, str, str]]:
    transactions = db.scalars(
        select(FinancialTransaction).where(FinancialTransaction.user_id == user_id)
    )
    return {
        transaction_fingerprint(
            transaction_date=transaction.transaction_date,
            amount=Decimal(str(transaction.amount)),
            description=transaction.description,
            transaction_type=transaction.type,
        )
        for transaction in transactions
    }


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold().strip())
    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_accents).split())
