import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.password_reset_token import PasswordResetToken
from backend.models.user import User
from backend.services.auth_service import normalize_email, password_hasher


DEFAULT_PASSWORD_RESET_EXPIRATION_MINUTES = 30
MIN_PASSWORD_RESET_EXPIRATION_MINUTES = 5
MAX_PASSWORD_RESET_EXPIRATION_MINUTES = 1440


class InvalidPasswordResetTokenError(ValueError):
    pass


class PasswordResetConfigurationError(RuntimeError):
    pass


def create_password_reset_token(
    db: Session,
    *,
    email: str,
    current_time: datetime | None = None,
) -> tuple[str, str] | None:
    expiration_minutes = _expiration_minutes()
    normalized_email = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized_email))
    if (
        user is None
        or not user.active
        or user.email is None
        or user.password_hash is None
    ):
        _token_hash(secrets.token_urlsafe(48))
        return None

    now = current_time or datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(48)
    token_hash = _token_hash(raw_token)
    expires_at = now + timedelta(minutes=expiration_minutes)
    reset_token = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id)
        .with_for_update()
    )
    if reset_token is None:
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            used_at=None,
            created_at=now,
        )
        db.add(reset_token)
    else:
        reset_token.token_hash = token_hash
        reset_token.expires_at = expires_at
        reset_token.used_at = None
        reset_token.created_at = now

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        reset_token = db.scalar(
            select(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id)
            .with_for_update()
        )
        if reset_token is None:
            raise
        reset_token.token_hash = token_hash
        reset_token.expires_at = expires_at
        reset_token.used_at = None
        reset_token.created_at = now
        db.commit()
    return user.email, raw_token


def reset_password_with_token(
    db: Session,
    *,
    raw_token: str,
    new_password: str,
    current_time: datetime | None = None,
) -> None:
    now = current_time or datetime.now(timezone.utc)
    reset_token = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == _token_hash(raw_token))
        .with_for_update()
    )
    if (
        reset_token is None
        or reset_token.used_at is not None
        or _as_utc(reset_token.expires_at) <= _as_utc(now)
    ):
        raise InvalidPasswordResetTokenError(
            "Token de recuperação inválido ou expirado"
        )

    user = db.get(User, reset_token.user_id)
    if user is None or not user.active or user.password_hash is None:
        raise InvalidPasswordResetTokenError(
            "Token de recuperação inválido ou expirado"
        )

    user.password_hash = password_hasher.hash(new_password)
    reset_token.used_at = now
    db.commit()


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _expiration_minutes() -> int:
    raw_value = os.getenv(
        "PASSWORD_RESET_EXPIRE_MINUTES",
        str(DEFAULT_PASSWORD_RESET_EXPIRATION_MINUTES),
    )
    try:
        minutes = int(raw_value)
    except ValueError as exc:
        raise PasswordResetConfigurationError(
            "PASSWORD_RESET_EXPIRE_MINUTES inválida"
        ) from exc
    if not (
        MIN_PASSWORD_RESET_EXPIRATION_MINUTES
        <= minutes
        <= MAX_PASSWORD_RESET_EXPIRATION_MINUTES
    ):
        raise PasswordResetConfigurationError(
            "PASSWORD_RESET_EXPIRE_MINUTES inválida"
        )
    return minutes


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
