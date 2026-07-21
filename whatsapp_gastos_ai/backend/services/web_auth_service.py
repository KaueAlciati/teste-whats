from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.services.autorizacao_service import liberar_usuario
from backend.services.db_init import conectar_bd

logger = logging.getLogger(__name__)

UTC = timezone.utc
ACCESS_COOKIE = "fc_access_token"
REFRESH_COOKIE = "fc_refresh_token"
SESSION_COOKIE = "fc_session_id"
DEFAULT_ACCESS_MINUTES = int(os.getenv("WEB_ACCESS_TOKEN_MINUTES", "60"))
DEFAULT_REFRESH_DAYS = int(os.getenv("WEB_REFRESH_TOKEN_DAYS", "7"))


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

    @property
    def display_name(self) -> str:
        return self.nome or self.email or self.telefone or f"Usuário {self.id}"


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
    salt = _b64url_decode(salt_b64) if salt_b64 else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return digest.hex(), _b64url_encode(salt)


def hash_password(password: str) -> tuple[str, str]:
    return _password_hash(password)


def verify_password(password: str, salt_b64: str, expected_hash: str) -> bool:
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
    )


def fetch_user_by_identifier(identifier: str) -> WebUser | None:
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome, telefone, email, schema_user, autorizado, web_active, web_role, web_avatar_url
            FROM usuarios
            WHERE telefone = %s OR LOWER(email) = LOWER(%s)
            LIMIT 1
            """,
            (identifier, identifier),
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
            SELECT id, nome, telefone, email, schema_user, autorizado, web_active, web_role, web_avatar_url
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

    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE usuarios
            SET nome = COALESCE(%s, nome),
                email = COALESCE(%s, email),
                senha_hash = %s,
                senha_salt = %s,
                web_active = true,
                web_role = %s,
                autorizado = true,
                schema_user = COALESCE(%s, schema_user),
                web_last_login = NULL
            WHERE telefone = %s
            """,
            (name, email, password_hash, salt, role, schema, phone),
        )
        conn.commit()
        cursor.execute(
            """
            SELECT id, nome, telefone, email, schema_user, autorizado, web_active, web_role, web_avatar_url
            FROM usuarios
            WHERE telefone = %s
            LIMIT 1
            """,
            (phone,),
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
            "UPDATE usuarios SET web_last_login = NOW() WHERE id = %s",
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
        raise ValueError("Usuário não encontrado.")
    if not user.web_active:
        raise ValueError("Usuário web desativado.")

    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT senha_hash, senha_salt FROM usuarios WHERE id = %s",
            (user.id,),
        )
        row = cursor.fetchone()
        if not row or not row[0] or not row[1]:
            raise ValueError("Usuário sem senha cadastrada.")
        if not verify_password(password, row[1], row[0]):
            raise ValueError("Credenciais inválidas.")
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
    if not user.web_active:
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
        "display_name": user.display_name,
        "telefone": user.telefone,
        "email": user.email,
        "schema_user": user.schema_user,
        "web_role": user.web_role,
        "web_avatar_url": user.web_avatar_url,
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
