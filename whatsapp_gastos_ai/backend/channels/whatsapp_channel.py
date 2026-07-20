from __future__ import annotations

import logging
from typing import Any

from backend.core.agent import process_agent_message
from backend.core.models import AgentResponse, IncomingMessage
from backend.services.whatsapp_service import (
    enviar_imagem_whatsapp,
    enviar_lista_interativa,
    enviar_mensagem_whatsapp,
)

logger = logging.getLogger(__name__)


def build_incoming_message_from_meta(payload: dict[str, Any]) -> IncomingMessage | None:
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages", [])
        if not messages:
            return None
        message = messages[0]
        message_type = message.get("type", "text")
        user_id = str(message.get("from"))
        text = None
        media_id = None
        file_name = None

        if message_type == "text":
            text = message.get("text", {}).get("body")
        elif message_type in {"image", "document", "audio"}:
            media = message.get(message_type, {})
            media_id = media.get("id")
            file_name = media.get("filename")
        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                text = interactive.get("button_reply", {}).get("id")
            elif interactive.get("type") == "list_reply":
                text = interactive.get("list_reply", {}).get("id")
        elif message_type == "location":
            location = message.get("location", {})
            text = f"{location.get('latitude')},{location.get('longitude')}"

        return IncomingMessage(
            user_id=user_id,
            channel="whatsapp",
            message_type=message_type,
            text=text,
            media_id=media_id,
            file_name=file_name,
            raw_payload=payload,
            metadata={"message_id": message.get("id"), "timestamp": message.get("timestamp")},
        )
    except Exception:
        logger.exception("Falha ao normalizar payload da Meta.")
        return None


async def send_agent_response_whatsapp(user_id: str, response: AgentResponse) -> None:
    if response.transfer_to_human:
        await enviar_mensagem_whatsapp(user_id, response.text or "Encaminhado para atendimento humano.")
        return

    if response.options:
        opcoes = response.options[:3]
        if len(opcoes) <= 3:
            texto = response.text or ""
            linhas = [f"• {op.get('label') or op.get('title') or op.get('id')}" for op in opcoes]
            await enviar_mensagem_whatsapp(user_id, "\n".join([texto] + linhas if texto else linhas))
            return
        secoes = [{"title": "Opções", "rows": [{"id": str(opt.get("id")), "title": str(opt.get("label") or opt.get("title") or opt.get("id"))} for opt in opcoes]}]
        await enviar_lista_interativa(user_id, response.text or "Opções", response.text or "", "Ver opções", secoes)
        return

    if response.image_path:
        await enviar_imagem_whatsapp(user_id, response.image_path, response.text)
        return

    if response.document_path:
        await enviar_mensagem_whatsapp(user_id, response.text or "Documento gerado.")
        return

    await enviar_mensagem_whatsapp(user_id, response.text or "")


async def handle_incoming_whatsapp_message(payload: dict[str, Any]) -> IncomingMessage | None:
    message = build_incoming_message_from_meta(payload)
    if not message:
        return None
    response = await process_agent_message(message)
    await send_agent_response_whatsapp(message.user_id, response)
    return message
