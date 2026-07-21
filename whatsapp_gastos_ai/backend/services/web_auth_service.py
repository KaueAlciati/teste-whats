from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import bcrypt
except Exception:  # pragma: no cover - fallback only
    bcrypt = None

from backend.services.autorizacao_service import liberar_usuario
from backend.services.db_init import conectar_bd

logger = logging.getLogger(__name__)

UTC = timezone.utc
ACCESS_COOKIE = "fc_access_token"
REFRESH_COOKIE = "fc_refresh_token"
SESSION_COOKIE = "fc_session_id"
DEFAULT_ACCESS_MINUTES = int(os.getenv("WEB_ACCESS_TOKEN_MINUTES", "60"))
DEFAULT_REFRESH_DAYS = int(os.getenv("WEB_REFRESH_TOKEN_DAYS", "7"))
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"\D+")


@dataclass(slots=True)
class WebUser:
    id: int
    nome: str | None
    telefone: str | None
    email: str | None
    schema_user: str | None
    autorizado: bool
    web_active: bool
    web_role: str | None
    web_avatar_url: str | None
    email_verified: bool = False
    phone_verified: bool = False
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login_at: datetime | None = None

    @property
    def display_name(self) -> str:
        return self.nome or self.email or self.telefone or f"Usuário {self.id}"

    @property
    def name(self) -> str | None:
        return self.nome

    @property
    def phone(self) -> str | None:
        return self.telefone


def _get_secret() -> str:
    secret = os.getenv("WEB_JWT_SECRET") or os.getenv("JWT_SECRET") or os.getenv("VERIFY_TOKEN")
    if not secret:
        raise RuntimeError("WEB_JWT_SECRET não configurado.")
    return secret


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _signing_input(header: dict[str, Any], payload: dict[str, Any]) -> bytes:
    return f"{_b64url_encode(json.dumps(header, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))}.{_b64url_encode(json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))}".encode("ascii")


def _encode_jwt(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = _signing_input(header, payload)
    signature = hmac.new(_get_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{signing_input.decode('ascii')}.{_b64url_encode(signature)}"


def _decode_jwt(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(_get_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
            raise ValueError("Assinatura inválida.")
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        exp = payload.get("exp")
        if exp and datetime.now(UTC).timestamp() > float(exp):
            raise ValueError("Token expirado.")
        return payload
    except Exception as exc:
        raise ValueError("Token inválido.") from exc


def _now() -> datetime:
    return datetime.now(UTC)


def _password_hash(password: str, salt_b64: str | None = None) -> tuple[str, str]:
    if bcrypt is not None:
        if salt_b64:
            salt = _b64url_decode(salt_b64)
            if len(salt) == 16:
                hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(prefix=b"2b"))
                return hashed.decode("utf-8"), _b64url_encode(salt)
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
        return hashed.decode("utf-8"), ""
    salt = _b64url_decode(salt_b64) if salt_b64 else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return digest.hex(), _b64url_encode(salt)


def hash_password(password: str) -> tuple[str, str]:
    return _password_hash(password)


def verify_password(password: str, salt_b64: str, expected_hash: str) -> bool:
    if bcrypt is not None and expected_hash and expected_hash.startswith("$2"):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), expected_hash.encode("utf-8"))
        except Exception:
            return False
    computed, _ = _password_hash(password, salt_b64)
    return hmac.compare_digest(computed, expected_hash or "")


def _row_to_user(row: tuple[Any, ...]) -> WebUser:
    return WebUser(
        id=row[0],
        nome=row[1],
        telefone=row[2],
        email=row[3],
        schema_user=row[4],
        autorizado=bool(row[5]),
        web_active=bool(row[6]),
        web_role=row[7],
        web_avatar_url=row[8],
        email_verified=bool(row[9]) if len(row) > 9 else False,
        phone_verified=bool(row[10]) if len(row) > 10 else False,
        is_active=bool(row[11]) if len(row) > 11 else bool(row[6]),
        created_at=row[12] if len(row) > 12 else None,
        updated_at=row[13] if len(row) > 13 else None,
        last_login_at=row[14] if len(row) > 14 else None,
    )


def fetch_user_by_identifier(identifier: str) -> WebUser | None:
    normalized_phone = normalize_phone_number(identifier)
    normalized_email = _normalize_email(identifier)
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, COALESCE(name, nome), COALESCE(phone, telefone), email, schema_user,
                   COALESCE(autorizado, true), COALESCE(web_active, is_active, true), web_role, web_avatar_url,
                   COALESCE(email_verified, false), COALESCE(phone_verified, false), COALESCE(is_active, web_active, true),
                   created_at, updated_at, COALESCE(last_login_at, web_last_login)
            FROM usuarios
            WHERE COALESCE(phone, telefone) = %s
               OR LOWER(email) = LOWER(%s)
            LIMIT 1
            """,
            (normalized_phone or identifier, normalized_email or identifier),
        )
        row = cursor.fetchone()
        return _row_to_user(row) if row else None
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def fetch_user_by_id(user_id: int) -> WebUser | None:
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, COALESCE(name, nome), COALESCE(phone, telefone), email, schema_user,
                   COALESCE(autorizado, true), COALESCE(web_active, is_active, true), web_role, web_avatar_url,
                   COALESCE(email_verified, false), COALESCE(phone_verified, false), COALESCE(is_active, web_active, true),
                   created_at, updated_at, COALESCE(last_login_at, web_last_login)
            FROM usuarios
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        return _row_to_user(row) if row else None
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def upsert_web_user(
    *,
    name: str,
    phone: str,
    email: str,
    password: str,
    schema: str | None = None,
    role: str = "admin",
) -> WebUser:
    if not phone:
        raise ValueError("Telefone é obrigatório para vincular o usuário ao schema financeiro.")

    liberar_usuario(name or "Fincontrol", phone)
    password_hash, salt = hash_password(password)
    normalized_phone = normalize_phone_number(phone) or phone

    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE usuarios
            SET nome = COALESCE(%s, nome),
                name = COALESCE(%s, name),
                email = COALESCE(%s, email),
                telefone = COALESCE(%s, telefone),
                phone = COALESCE(%s, phone),
                senha_hash = %s,
                password_hash = %s,
                senha_salt = %s,
                web_active = true,
                is_active = true,
                web_role = %s,
                autorizado = true,
                schema_user = COALESCE(%s, schema_user),
                web_last_login = NULL,
                last_login_at = NULL,
                updated_at = NOW()
            WHERE telefone = %s
            """,
            (name, name, email, normalized_phone, normalized_phone, password_hash, password_hash, salt, role, schema, normalized_phone),
        )
        conn.commit()
        cursor.execute(
            """
            SELECT id, COALESCE(name, nome), COALESCE(phone, telefone), email, schema_user,
                   COALESCE(autorizado, true), COALESCE(web_active, is_active, true), web_role, web_avatar_url,
                   COALESCE(email_verified, false), COALESCE(phone_verified, false), COALESCE(is_active, web_active, true),
                   created_at, updated_at, COALESCE(last_login_at, web_last_login)
            FROM usuarios
            WHERE telefone = %s
            LIMIT 1
            """,
            (normalized_phone,),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Não foi possível criar ou atualizar o usuário web.")
        logger.info("Usuário web provisionado: %s", phone)
        return _row_to_user(row)
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def bootstrap_web_admin() -> WebUser | None:
    name = os.getenv("WEB_ADMIN_NAME")
    phone = os.getenv("WEB_ADMIN_PHONE")
    email = os.getenv("WEB_ADMIN_EMAIL")
    password = os.getenv("WEB_ADMIN_PASSWORD")
    schema = os.getenv("WEB_ADMIN_SCHEMA")

    if not any([name, phone, email, password]):
        return None
    if not all([phone, email, password]):
        logger.warning("Bootstrap web ignorado: configure WEB_ADMIN_PHONE, WEB_ADMIN_EMAIL e WEB_ADMIN_PASSWORD.")
        return None

    user = upsert_web_user(
        name=name or "Fincontrol",
        phone=phone,
        email=email,
        password=password,
        schema=schema,
        role="admin",
    )
    logger.info("Bootstrap do usuário web concluído: %s", user.display_name)
    return user


def normalize_phone_number(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = PHONE_RE.sub("", phone)
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) in {10, 11} and not digits.startswith("55"):
        digits = f"55{digits}"
    return digits


def _normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    normalized = email.strip().lower()
    return normalized or None


def _ensure_financial_schema(cursor, schema: str) -> None:
    safe_schema = "".join(ch for ch in schema if ch.isalnum() or ch == "_")
    if not safe_schema:
        raise ValueError("Nome de schema inválido.")
    if safe_schema[0].isdigit():
        safe_schema = f"user_{safe_schema}"
    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{safe_schema}"')
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{safe_schema}".gastos (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor REAL,
            categoria TEXT,
            meio_pagamento TEXT,
            parcelas INT DEFAULT 1,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{safe_schema}".receitas (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor REAL NOT NULL,
            origem TEXT,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{safe_schema}".fatura_cartao (
            id SERIAL PRIMARY KEY,
            descricao TEXT,
            valor REAL,
            categoria TEXT,
            meio_pagamento TEXT,
            parcela TEXT,
            data_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_fim DATE
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{safe_schema}".lembretes (
            id SERIAL PRIMARY KEY,
            telefone TEXT,
            mensagem TEXT,
            cron TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{safe_schema}".salario (
            id SERIAL PRIMARY KEY,
            valor REAL,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{safe_schema}".email (
            id SERIAL PRIMARY KEY,
            telefone TEXT NOT NULL,
            email_user TEXT NOT NULL,
            email_pass TEXT NOT NULL,
            descricao TEXT,
            data_inclusao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _user_select_columns() -> str:
    return """
        id,
        COALESCE(name, nome) AS nome,
        COALESCE(phone, telefone) AS telefone,
        email,
        schema_user,
        COALESCE(autorizado, true) AS autorizado,
        COALESCE(web_active, is_active, true) AS web_active,
        web_role,
        web_avatar_url
    """


def _row_to_user(row: tuple[Any, ...]) -> WebUser:
    return WebUser(
        id=row[0],
        nome=row[1],
        telefone=row[2],
        email=row[3],
        schema_user=row[4],
        autorizado=bool(row[5]),
        web_active=bool(row[6]),
        web_role=row[7],
        web_avatar_url=row[8],
    )


def _fetch_user_row(cursor, sql: str, params: tuple[Any, ...]) -> WebUser | None:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return _row_to_user(row) if row else None


def register_web_user(name: str, email: str, phone: str, password: str) -> WebUser:
    normalized_phone = normalize_phone_number(phone)
    normalized_email = _normalize_email(email)
    if not name.strip():
        raise ValueError("Nome é obrigatório.")
    if not normalized_email or not EMAIL_RE.match(normalized_email):
        raise ValueError("E-mail inválido.")
    if not normalized_phone:
        raise ValueError("Telefone inválido.")
    if len(password or "") < 8:
        raise ValueError("Senha muito curta.")

    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id
            FROM usuarios
            WHERE LOWER(email) = LOWER(%s)
               OR COALESCE(phone, telefone) = %s
            LIMIT 1
            """,
            (normalized_email, normalized_phone),
        )
        if cursor.fetchone():
            raise ValueError("Conta já cadastrada.")

        password_hash, salt = hash_password(password)
        cursor.execute(
            """
            INSERT INTO usuarios (
                nome, name, email, telefone, phone,
                senha_hash, password_hash, senha_salt,
                is_active, email_verified, phone_verified,
                web_active, web_role, autorizado,
                created_at, updated_at, last_login_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                true, false, false,
                true, 'user', true,
                NOW(), NOW(), NULL
            )
            RETURNING id
            """,
            (name.strip(), name.strip(), normalized_email, normalized_phone, normalized_phone, password_hash, password_hash, salt),
        )
        user_id = cursor.fetchone()[0]
        schema = f"user_{user_id}"
        _ensure_financial_schema(cursor, schema)
        cursor.execute(
            """
            UPDATE usuarios
            SET schema_user = %s,
                updated_at = NOW(),
                web_active = true,
                is_active = true,
                autorizado = true
            WHERE id = %s
            """,
            (schema, user_id),
        )
        conn.commit()
        logger.info("Usuário registrado: %s / %s", normalized_email, normalized_phone)
        user = fetch_user_by_id(user_id)
        if not user:
            raise RuntimeError("Não foi possível carregar o usuário criado.")
        return user
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def request_email_verification_for_user(user_id: int) -> dict[str, Any]:
    token = secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = _now() + timedelta(hours=24)
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_email_verification_tokens (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (token_hash) DO UPDATE
            SET user_id = EXCLUDED.user_id,
                expires_at = EXCLUDED.expires_at,
                verified_at = NULL
            """,
            (user_id, token_hash, expires_at),
        )
        cursor.execute(
            """
            UPDATE usuarios
            SET email_verified = false,
                updated_at = NOW()
            WHERE id = %s
            """,
            (user_id,),
        )
        conn.commit()
        return {"token": token, "expires_at": expires_at}
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def verify_email_token(email: str, token: str) -> bool:
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return False
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT u.id
            FROM usuarios u
            JOIN user_email_verification_tokens t ON t.user_id = u.id
            WHERE LOWER(u.email) = LOWER(%s)
              AND t.token_hash = %s
              AND t.expires_at > NOW()
              AND t.verified_at IS NULL
            LIMIT 1
            """,
            (normalized_email, token_hash),
        )
        row = cursor.fetchone()
        if not row:
            return False
        user_id = row[0]
        cursor.execute(
            """
            UPDATE usuarios
            SET email_verified = true,
                updated_at = NOW()
            WHERE id = %s
            """,
            (user_id,),
        )
        cursor.execute(
            """
            UPDATE user_email_verification_tokens
            SET verified_at = NOW()
            WHERE token_hash = %s
            """,
            (token_hash,),
        )
        conn.commit()
        return True
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def create_channel_link_code(user_id: int, channel: str) -> dict[str, Any]:
    code = f"{secrets.randbelow(900000) + 100000:06d}"
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    expires_at = _now() + timedelta(minutes=10)
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_channels (user_id, channel, is_verified, verification_code_hash, verification_expires_at, created_at, last_seen_at)
            VALUES (%s, %s, false, %s, %s, NOW(), NOW())
            ON CONFLICT (user_id, channel) DO UPDATE
            SET is_verified = false,
                verification_code_hash = EXCLUDED.verification_code_hash,
                verification_expires_at = EXCLUDED.verification_expires_at,
                channel_user_id = NULL,
                phone_number = NULL,
                username = NULL,
                display_name = NULL,
                linked_at = NULL,
                last_seen_at = NOW()
            """,
            (user_id, channel, code_hash, expires_at),
        )
        conn.commit()
        return {"code": code, "expires_at": expires_at}
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def get_channel_link_status(user_id: int, channel: str) -> dict[str, Any]:
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, channel, channel_user_id, phone_number, username, display_name, is_verified,
                   verification_expires_at, linked_at, last_seen_at, created_at
            FROM user_channels
            WHERE user_id = %s AND channel = %s
            LIMIT 1
            """,
            (user_id, channel),
        )
        row = cursor.fetchone()
        if not row:
            return {"linked": False, "pending": False, "channel": channel}
        expires_at = row[7]
        now = _now()
        return {
            "linked": bool(row[6]),
            "pending": bool(expires_at and not row[6] and expires_at > now),
            "expired": bool(expires_at and not row[6] and expires_at <= now),
            "channel": row[1],
            "user_id": row[0],
            "channel_user_id": row[2],
            "phone_number": row[3],
            "username": row[4],
            "display_name": row[5],
            "verification_expires_at": expires_at,
            "linked_at": row[8],
            "last_seen_at": row[9],
            "created_at": row[10],
        }
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def unlink_channel(user_id: int, channel: str) -> bool:
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM user_channels WHERE user_id = %s AND channel = %s",
            (user_id, channel),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def resolve_channel_link(channel: str, channel_user_id: str) -> dict[str, Any] | None:
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, channel_user_id, phone_number, username, display_name, is_verified, linked_at, last_seen_at
            FROM user_channels
            WHERE channel = %s AND channel_user_id = %s AND is_verified = true
            LIMIT 1
            """,
            (channel, channel_user_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        user = fetch_user_by_id(int(row[0]))
        if not user or not user.web_active:
            return None
        return {
            "user": user,
            "user_id": user.id,
            "channel_user_id": row[1],
            "phone_number": row[2],
            "username": row[3],
            "display_name": row[4],
            "linked_at": row[6],
            "last_seen_at": row[7],
        }
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def link_channel_by_code(
    channel: str,
    channel_user_id: str,
    code: str,
    *,
    username: str | None = None,
    display_name: str | None = None,
    phone_number: str | None = None,
) -> dict[str, Any]:
    token_hash = hashlib.sha256((code or "").strip().encode("utf-8")).hexdigest()
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_id
            FROM user_channels
            WHERE channel = %s
              AND verification_code_hash = %s
              AND verification_expires_at > NOW()
              AND is_verified = false
            LIMIT 1
            """,
            (channel, token_hash),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Código inválido ou expirado.")
        pending_id, user_id = row

        cursor.execute(
            """
            SELECT user_id
            FROM user_channels
            WHERE channel = %s
              AND channel_user_id = %s
              AND is_verified = true
            LIMIT 1
            """,
            (channel, channel_user_id),
        )
        already_linked = cursor.fetchone()
        if already_linked and int(already_linked[0]) != int(user_id):
            raise ValueError("Este canal já está vinculado a outra conta.")

        cursor.execute(
            """
            UPDATE user_channels
            SET channel_user_id = %s,
                phone_number = %s,
                username = %s,
                display_name = %s,
                is_verified = true,
                verification_code_hash = NULL,
                verification_expires_at = NULL,
                linked_at = NOW(),
                last_seen_at = NOW()
            WHERE id = %s
            """,
            (channel_user_id, phone_number, username, display_name, pending_id),
        )
        cursor.execute(
            """
            UPDATE usuarios
            SET updated_at = NOW(),
                phone_verified = true
            WHERE id = %s
            """,
            (user_id,),
        )
        conn.commit()
        return {"user_id": int(user_id), "channel": channel, "channel_user_id": channel_user_id}
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def _session_payload(user: WebUser, token_type: str, expires_in_seconds: int, session_id: str | None = None, jti: str | None = None) -> dict[str, Any]:
    now = _now()
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "name": user.display_name,
        "email": user.email,
        "phone": user.telefone,
        "schema": user.schema_user,
        "role": user.web_role or "user",
        "type": token_type,
        "iat": now.timestamp(),
        "exp": (now + timedelta(seconds=expires_in_seconds)).timestamp(),
    }
    if session_id:
        payload["sid"] = session_id
    if jti:
        payload["jti"] = jti
    return payload


def create_session_tokens(
    user: WebUser,
    *,
    remember_me: bool = False,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    refresh_days = DEFAULT_REFRESH_DAYS if remember_me else max(1, DEFAULT_REFRESH_DAYS // 2)
    access_seconds = max(15 * 60, DEFAULT_ACCESS_MINUTES * 60)
    session_id = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())
    refresh_expires_at = _now() + timedelta(days=refresh_days)

    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO web_auth_sessions (session_id, usuario_id, refresh_jti, refresh_expires_at, user_agent, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (session_id, user.id, refresh_jti, refresh_expires_at, user_agent, ip_address),
        )
        cursor.execute(
            """
            UPDATE usuarios
            SET web_last_login = NOW(),
                last_login_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (user.id,),
        )
        conn.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

    access_token = _encode_jwt(_session_payload(user, "access", access_seconds, session_id=session_id))
    refresh_token = _encode_jwt(_session_payload(user, "refresh", refresh_days * 24 * 60 * 60, session_id=session_id, jti=refresh_jti))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "session_id": session_id,
        "expires_in": access_seconds,
        "refresh_expires_in": refresh_days * 24 * 60 * 60,
    }


def authenticate_web_user(identifier: str, password: str, *, remember_me: bool = False, user_agent: str | None = None, ip_address: str | None = None) -> dict[str, Any]:
    user = fetch_user_by_identifier(identifier)
    if not user:
        raise ValueError("E-mail, telefone ou senha inválidos.")
    if not user.web_active or not user.is_active:
        raise ValueError("E-mail, telefone ou senha inválidos.")

    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(password_hash, senha_hash), senha_salt, COALESCE(is_active, web_active, true) FROM usuarios WHERE id = %s",
            (user.id,),
        )
        row = cursor.fetchone()
        if not row or not row[0] or not row[1] or not bool(row[2]):
            raise ValueError("E-mail, telefone ou senha inválidos.")
        if not verify_password(password, row[1], row[0]):
            raise ValueError("E-mail, telefone ou senha inválidos.")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

    tokens = create_session_tokens(user, remember_me=remember_me, user_agent=user_agent, ip_address=ip_address)
    return {"user": user, **tokens}


def get_user_from_access_token(token: str) -> WebUser:
    payload = _decode_jwt(token)
    if payload.get("type") != "access":
        raise ValueError("Token de acesso inválido.")
    user = fetch_user_by_id(int(payload["sub"]))
    if not user:
        raise ValueError("Usuário não encontrado.")
    if not user.web_active or not user.is_active:
        raise ValueError("Usuário web desativado.")
    return user


def refresh_session(refresh_token: str) -> dict[str, Any]:
    payload = _decode_jwt(refresh_token)
    if payload.get("type") != "refresh":
        raise ValueError("Token de refresh inválido.")

    session_id = payload.get("sid")
    refresh_jti = payload.get("jti")
    if not session_id or not refresh_jti:
        raise ValueError("Sessão inválida.")

    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT usuario_id
            FROM web_auth_sessions
            WHERE session_id = %s AND refresh_jti = %s AND revoked_at IS NULL AND refresh_expires_at > NOW()
            LIMIT 1
            """,
            (session_id, refresh_jti),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Sessão expirada ou revogada.")
        user = fetch_user_by_id(int(row[0]))
        if not user:
            raise ValueError("Usuário não encontrado.")
        tokens = create_session_tokens(user, remember_me=True)
        return {"user": user, **tokens}
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def revoke_session(refresh_token: str | None = None, session_id: str | None = None) -> None:
    if not refresh_token and not session_id:
        return

    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        if refresh_token:
            try:
                payload = _decode_jwt(refresh_token)
                session_id = session_id or payload.get("sid")
                refresh_jti = payload.get("jti")
            except Exception:
                session_id = session_id or None
                refresh_jti = None
        else:
            refresh_jti = None

        if session_id and refresh_jti:
            cursor.execute(
                """
                UPDATE web_auth_sessions
                SET revoked_at = NOW(), last_seen_at = NOW()
                WHERE session_id = %s AND refresh_jti = %s AND revoked_at IS NULL
                """,
                (session_id, refresh_jti),
            )
        elif session_id:
            cursor.execute(
                """
                UPDATE web_auth_sessions
                SET revoked_at = NOW(), last_seen_at = NOW()
                WHERE session_id = %s AND revoked_at IS NULL
                """,
                (session_id,),
            )
        conn.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def safe_user_dict(user: WebUser) -> dict[str, Any]:
    return {
        "id": user.id,
        "nome": user.nome,
        "name": user.name,
        "display_name": user.display_name,
        "telefone": user.telefone,
        "phone": user.phone,
        "email": user.email,
        "schema_user": user.schema_user,
        "web_role": user.web_role,
        "web_avatar_url": user.web_avatar_url,
        "email_verified": user.email_verified,
        "phone_verified": user.phone_verified,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if isinstance(user.created_at, datetime) else None,
        "updated_at": user.updated_at.isoformat() if isinstance(user.updated_at, datetime) else None,
        "last_login_at": user.last_login_at.isoformat() if isinstance(user.last_login_at, datetime) else None,
    }


def build_avatar_label(name: str | None, fallback: str | None = None) -> str:
    base = (name or fallback or "FC").strip()
    pieces = [part for part in base.replace("@", " ").replace("-", " ").split() if part]
    if not pieces:
        return "FC"
    if len(pieces) == 1:
        letters = pieces[0][:2]
    else:
        letters = pieces[0][0] + pieces[-1][0]
    return letters.upper()
