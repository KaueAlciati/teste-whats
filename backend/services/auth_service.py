import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.user import User
from backend.services.user_service import normalize_whatsapp_phone


JWT_ALGORITHM = "HS256"
JWT_ISSUER = "fincontrol-ai"
JWT_AUDIENCE = "fincontrol-ai-api"
DEFAULT_TOKEN_EXPIRATION_MINUTES = 60
MINIMUM_JWT_SECRET_LENGTH = 32

password_hasher = PasswordHasher()


class DuplicateEmailError(ValueError):
    pass


class DuplicateWhatsAppPhoneError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class AuthConfigurationError(RuntimeError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def register_user(
    db: Session,
    *,
    name: str,
    email: str,
    whatsapp_phone: str,
    password: str,
) -> User:
    normalized_email = normalize_email(email)
    normalized_phone = normalize_whatsapp_phone(whatsapp_phone)

    if db.scalar(select(User).where(User.email == normalized_email)) is not None:
        raise DuplicateEmailError("E-mail já cadastrado")

    phone_user = db.scalar(
        select(User).where(User.whatsapp_phone == normalized_phone)
    )
    if phone_user is not None and (
        phone_user.email is not None or phone_user.password_hash is not None
    ):
        raise DuplicateWhatsAppPhoneError("WhatsApp já cadastrado")

    hashed_password = password_hasher.hash(password)
    if phone_user is None:
        user = User(
            name=name,
            email=normalized_email,
            whatsapp_phone=normalized_phone,
            password_hash=hashed_password,
            whatsapp_verified=False,
        )
        db.add(user)
    else:
        user = phone_user
        user.name = name
        user.email = normalized_email
        user.password_hash = hashed_password

    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as exc:
        db.rollback()
        if db.scalar(select(User).where(User.email == normalized_email)) is not None:
            raise DuplicateEmailError("E-mail já cadastrado") from exc
        if (
            db.scalar(
                select(User).where(User.whatsapp_phone == normalized_phone)
            )
            is not None
        ):
            raise DuplicateWhatsAppPhoneError("WhatsApp já cadastrado") from exc
        raise


def authenticate_user(db: Session, *, email: str, password: str) -> User:
    normalized_email = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized_email))
    if (
        user is None
        or user.password_hash is None
        or not user.active
        or not _verify_password(user.password_hash, password)
    ):
        raise InvalidCredentialsError("E-mail ou senha inválidos")

    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(password)
        db.commit()
        db.refresh(user)
    return user


def create_access_token(user: User) -> str:
    secret = _jwt_secret()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=_token_expiration_minutes())
    return jwt.encode(
        {
            "sub": str(user.id),
            "type": "access",
            "iat": now,
            "exp": expires_at,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "jti": uuid4().hex,
        },
        secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["sub", "type", "iat", "exp"]},
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidCredentialsError("Token inválido") from exc

    if payload.get("type") != "access":
        raise InvalidCredentialsError("Token inválido")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidCredentialsError("Token inválido") from exc
    if user_id <= 0:
        raise InvalidCredentialsError("Token inválido")
    return user_id


def get_active_user_by_id(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or not user.active:
        raise InvalidCredentialsError("Token inválido")
    return user


def _verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret) < MINIMUM_JWT_SECRET_LENGTH:
        raise AuthConfigurationError("JWT_SECRET_KEY não configurada com segurança")
    return secret


def _token_expiration_minutes() -> int:
    raw_value = os.getenv(
        "JWT_EXPIRE_MINUTES",
        str(DEFAULT_TOKEN_EXPIRATION_MINUTES),
    )
    try:
        minutes = int(raw_value)
    except ValueError as exc:
        raise AuthConfigurationError("JWT_EXPIRE_MINUTES inválido") from exc
    if not 1 <= minutes <= 1440:
        raise AuthConfigurationError("JWT_EXPIRE_MINUTES inválido")
    return minutes
