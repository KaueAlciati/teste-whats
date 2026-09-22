import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models.financial_transaction import FinancialTransaction
from backend.models.transaction_attachment import TransactionAttachment


MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
SUPPORTED_ATTACHMENTS = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}


class AttachmentStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedAttachment:
    content: bytes
    original_filename: str
    mime_type: str
    extension: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class StoredAttachment:
    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str


def validate_attachment(
    content: bytes,
    *,
    filename: str,
    mime_type: str | None,
) -> ValidatedAttachment:
    if not content:
        raise AttachmentStorageError("Arquivo vazio")
    if len(content) > MAX_ATTACHMENT_SIZE:
        raise AttachmentStorageError("O arquivo excede o limite de 10 MB")

    original_filename = _safe_original_filename(filename)
    extension = Path(original_filename).suffix.casefold()
    expected = SUPPORTED_ATTACHMENTS.get(extension)
    if expected is None:
        raise AttachmentStorageError(
            "Formato de comprovante não suportado. Use PDF, JPG, JPEG ou PNG"
        )
    expected_mime_type, signature = expected
    if not content.startswith(signature):
        raise AttachmentStorageError(
            "O conteúdo do arquivo não corresponde ao formato"
        )
    declared_mime_type = (mime_type or "").casefold().strip()
    if declared_mime_type and declared_mime_type not in {
        expected_mime_type,
        "application/octet-stream",
    }:
        raise AttachmentStorageError(
            "Tipo do arquivo não corresponde à extensão"
        )

    return ValidatedAttachment(
        content=content,
        original_filename=original_filename,
        mime_type=expected_mime_type,
        extension=extension,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def store_attachment_file(
    attachment: ValidatedAttachment,
    *,
    user_id: int,
) -> StoredAttachment:
    return _write_attachment_file(
        attachment,
        user_id=user_id,
        prefix="users",
    )


def stage_attachment_file(
    attachment: ValidatedAttachment,
    *,
    user_id: int,
) -> StoredAttachment:
    return _write_attachment_file(
        attachment,
        user_id=user_id,
        prefix="pending/users",
    )


def promote_staged_attachment(
    staged: StoredAttachment,
    *,
    user_id: int,
) -> StoredAttachment:
    expected_prefix = f"pending/users/{user_id}/"
    if not staged.storage_key.startswith(expected_prefix):
        raise AttachmentStorageError("Anexo pendente inválido")
    staged_path = _storage_path(staged.storage_key)
    try:
        content = staged_path.read_bytes()
    except OSError as exc:
        raise AttachmentStorageError(
            "Arquivo pendente do comprovante não está disponível"
        ) from exc
    if len(content) != staged.size_bytes:
        raise AttachmentStorageError("Arquivo pendente está corrompido")
    if hashlib.sha256(content).hexdigest() != staged.sha256:
        raise AttachmentStorageError("Arquivo pendente está corrompido")
    validated = validate_attachment(
        content,
        filename=staged.original_filename,
        mime_type=staged.mime_type,
    )
    return store_attachment_file(validated, user_id=user_id)


def _write_attachment_file(
    attachment: ValidatedAttachment,
    *,
    user_id: int,
    prefix: str,
) -> StoredAttachment:
    identifier = uuid4().hex
    storage_key = (
        f"{prefix}/{user_id}/{identifier[:2]}/"
        f"{identifier}{attachment.extension}"
    )
    target = _storage_path(storage_key)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as file_handle:
            file_handle.write(attachment.content)
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise AttachmentStorageError(
            "Não foi possível armazenar o comprovante"
        ) from exc

    return StoredAttachment(
        storage_key=storage_key,
        original_filename=attachment.original_filename,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
    )


def link_attachment_to_transactions(
    db: Session,
    *,
    user_id: int,
    transactions: list[FinancialTransaction],
    stored: StoredAttachment,
) -> list[TransactionAttachment]:
    attachments: list[TransactionAttachment] = []
    for transaction in transactions:
        if transaction.user_id != user_id:
            raise PermissionError("Transação pertence a outro usuário")
        if transaction.id is None:
            raise AttachmentStorageError("Transação ainda não foi persistida")
        attachment = TransactionAttachment(
            user_id=user_id,
            transaction_id=transaction.id,
            storage_key=stored.storage_key,
            original_filename=stored.original_filename,
            mime_type=stored.mime_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
        )
        db.add(attachment)
        attachments.append(attachment)
    return attachments


def get_transaction_attachment(
    db: Session,
    *,
    user_id: int,
    transaction_id: int,
) -> TransactionAttachment | None:
    return db.scalar(
        select(TransactionAttachment)
        .where(
            TransactionAttachment.user_id == user_id,
            TransactionAttachment.transaction_id == transaction_id,
        )
        .order_by(TransactionAttachment.id)
        .limit(1)
    )


def read_attachment_file(attachment: TransactionAttachment) -> bytes:
    path = _storage_path(attachment.storage_key)
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise AttachmentStorageError(
            "Arquivo do comprovante não está disponível"
        ) from exc
    if len(content) != attachment.size_bytes:
        raise AttachmentStorageError("Arquivo do comprovante está corrompido")
    if hashlib.sha256(content).hexdigest() != attachment.sha256:
        raise AttachmentStorageError("Arquivo do comprovante está corrompido")
    return content


def delete_stored_file(storage_key: str) -> None:
    try:
        _storage_path(storage_key).unlink(missing_ok=True)
    except OSError:
        pass


def delete_stored_file_if_unreferenced(db: Session, storage_key: str) -> None:
    attachment_id = db.scalar(
        select(TransactionAttachment.id)
        .where(TransactionAttachment.storage_key == storage_key)
        .limit(1)
    )
    if attachment_id is None:
        delete_stored_file(storage_key)


def remove_user_attachments(db: Session, *, user_id: int) -> list[str]:
    storage_keys = list(
        db.scalars(
            select(TransactionAttachment.storage_key)
            .where(TransactionAttachment.user_id == user_id)
            .distinct()
        )
    )
    db.execute(
        delete(TransactionAttachment).where(
            TransactionAttachment.user_id == user_id
        )
    )
    return storage_keys


def storage_root() -> Path:
    configured = os.getenv("ATTACHMENT_STORAGE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    railway_volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if railway_volume:
        return (Path(railway_volume) / "attachments").resolve()
    return (Path.cwd() / ".storage" / "attachments").resolve()


def _storage_path(storage_key: str) -> Path:
    root = storage_root()
    target = (root / storage_key).resolve()
    if not target.is_relative_to(root):
        raise AttachmentStorageError("Chave de armazenamento inválida")
    return target


def _safe_original_filename(filename: str) -> str:
    normalized = filename.replace("\\", "/").split("/")[-1]
    normalized = " ".join(normalized.replace("\r", " ").replace("\n", " ").split())
    if not normalized or len(normalized) > 255:
        raise AttachmentStorageError("Nome do arquivo inválido")
    return normalized
