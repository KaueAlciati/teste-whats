import logging
import os

import httpx


logger = logging.getLogger(__name__)


async def send_text_message(destino: str, texto: str) -> bool:
    token = os.getenv("WHATSAPP_TOKEN")
    phone_number_id = os.getenv("PHONE_NUMBER_ID")

    if not token or not phone_number_id:
        logger.error("Configuração do WhatsApp incompleta")
        return False

    url = f"https://graph.facebook.com/v25.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": destino,
        "type": "text",
        "text": {"body": texto},
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.RequestError:
        logger.error("Falha de rede ao enviar mensagem pelo WhatsApp")
        return False

    if response.is_error:
        logger.error(
            "Erro da API do WhatsApp: status=%s resposta=%s",
            response.status_code,
            response.text,
        )
        return False

    return True
