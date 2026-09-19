import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal, engine
from backend.models.user import User


logger = logging.getLogger("uvicorn.error")


def normalize_whatsapp_phone(whatsapp_phone: str) -> str:
    normalized_phone = "".join(
        character for character in whatsapp_phone if character.isdigit()
    )
    if not normalized_phone:
        raise ValueError("Número de WhatsApp inválido")
    return normalized_phone


def get_or_create_whatsapp_user(db: Session, whatsapp_phone: str) -> User:
    normalized_phone = normalize_whatsapp_phone(whatsapp_phone)
    user = db.scalar(
        select(User).where(User.whatsapp_phone == normalized_phone)
    )
    if user is not None:
        return user

    user = User(whatsapp_phone=normalized_phone)
    db.add(user)

    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        existing_user = db.scalar(
            select(User).where(User.whatsapp_phone == normalized_phone)
        )
        if existing_user is not None:
            return existing_user
        raise


def authorize_registered_whatsapp_user(
    db: Session,
    whatsapp_phone: str,
) -> User | None:
    normalized_phone = normalize_whatsapp_phone(whatsapp_phone)
    user = db.scalar(
        select(User).where(User.whatsapp_phone == normalized_phone)
    )

    if (
        user is None
        or not user.active
        or not user.email
        or not user.password_hash
    ):
        return None

    if not user.whatsapp_verified:
        user.whatsapp_verified = True
        db.commit()
        db.refresh(user)

    return user


def authorize_registered_whatsapp_phone(whatsapp_phone: str) -> bool:
    if engine is None:
        logger.error("Banco de dados não configurado para validar usuário")
        return False

    db = SessionLocal()
    try:
        return (
            authorize_registered_whatsapp_user(db, whatsapp_phone) is not None
        )
    except (SQLAlchemyError, ValueError):
        db.rollback()
        logger.error("Falha ao validar acesso do usuário do WhatsApp")
        return False
    finally:
        db.close()


def register_whatsapp_user(whatsapp_phone: str) -> bool:
    if engine is None:
        logger.error("Banco de dados não configurado para cadastro do usuário")
        return False

    db = SessionLocal()
    try:
        get_or_create_whatsapp_user(db, whatsapp_phone)
        return True
    except (SQLAlchemyError, ValueError):
        db.rollback()
        logger.error("Falha ao cadastrar usuário do WhatsApp")
        return False
    finally:
        db.close()
