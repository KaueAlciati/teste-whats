from __future__ import annotations

import logging
from typing import Any

from backend.services.db_init import conectar_bd

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 5000


def _normalizar_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content[:MAX_CONTENT_LENGTH]
    return str(content)[:MAX_CONTENT_LENGTH]


def salvar_mensagem_conversa(
    user_id: str,
    channel: str,
    direction: str,
    message_type: str,
    content: Any,
) -> None:
    texto = _normalizar_content(content)
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO conversation_messages (user_id, channel, direction, message_type, content)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, channel, direction, message_type, texto),
        )
        conn.commit()
        logger.info("Histórico salvo [%s] %s/%s", direction, channel, user_id)
    except Exception as exc:
        logger.exception("Erro ao salvar histórico de conversa [%s] %s/%s: %s", direction, channel, user_id, exc)
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def carregar_historico_conversa(user_id: str, channel: str, limite: int = 20) -> list[dict[str, Any]]:
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT direction, message_type, content
            FROM conversation_messages
            WHERE user_id = %s AND channel = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, channel, limite),
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        historico = [
            {
                "role": "assistant" if direction == "assistant" else "user",
                "content": content,
                "message_type": message_type,
            }
            for direction, message_type, content in reversed(rows)
        ]
        return historico
    except Exception as exc:
        logger.exception("Erro ao carregar histórico de conversa %s/%s: %s", channel, user_id, exc)
        return []
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def limpar_historico_conversa(user_id: str, channel: str) -> None:
    conn = None
    cursor = None
    try:
        conn = conectar_bd()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM conversation_messages WHERE user_id = %s AND channel = %s",
            (user_id, channel),
        )
        conn.commit()
        logger.info("Histórico apagado %s/%s", channel, user_id)
    except Exception as exc:
        logger.exception("Erro ao apagar histórico de conversa %s/%s: %s", channel, user_id, exc)
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
