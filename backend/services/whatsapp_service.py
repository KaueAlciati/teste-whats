import logging
import os

import httpx


logger = logging.getLogger("uvicorn.error")
GRAPH_API_VERSION = "v25.0"


async def send_text_message(destino: str, texto: str) -> bool:
    token = os.getenv("WHATSAPP_TOKEN")
    phone_number_id = os.getenv("PHONE_NUMBER_ID")

    if not token or not phone_number_id:
        logger.error("WHATSAPP_TOKEN configurado: %s", bool(token))
        logger.error("PHONE_NUMBER_ID configurado: %s", bool(phone_number_id))
        return False

    url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{phone_number_id}/messages"
    )
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

    logger.info("Tentando enviar resposta pelo WhatsApp")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.RequestError:
        logger.error("Falha de rede ao enviar mensagem pelo WhatsApp")
        return False
    except Exception:
        logger.error("Falha inesperada ao enviar mensagem pelo WhatsApp")
        return False

    logger.info(
        "Resposta da Meta: status HTTP=%s corpo=%s",
        response.status_code,
        response.text,
    )

    return not response.is_error


async def send_document_message(
    destino: str,
    *,
    content: bytes,
    filename: str,
    mime_type: str,
    caption: str | None = None,
) -> bool:
    token = os.getenv("WHATSAPP_TOKEN")
    phone_number_id = os.getenv("PHONE_NUMBER_ID")

    if not token or not phone_number_id:
        logger.error("WHATSAPP_TOKEN configurado: %s", bool(token))
        logger.error("PHONE_NUMBER_ID configurado: %s", bool(phone_number_id))
        return False
    if not content:
        logger.error("Documento do WhatsApp vazio")
        return False

    authorization = {"Authorization": f"Bearer {token}"}
    upload_url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{phone_number_id}/media"
    )
    message_url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{phone_number_id}/messages"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            upload_response = await client.post(
                upload_url,
                headers=authorization,
                data={"messaging_product": "whatsapp"},
                files={"file": (filename, content, mime_type)},
            )
            logger.info(
                "Upload de documento na Meta: status HTTP=%s corpo=%s",
                upload_response.status_code,
                upload_response.text,
            )
            if upload_response.is_error:
                return False

            try:
                media_id = upload_response.json().get("id")
            except ValueError:
                media_id = None
            if not isinstance(media_id, str) or not media_id:
                logger.error("Upload de documento sem media_id")
                return False

            document_payload: dict[str, str] = {
                "id": media_id,
                "filename": filename,
            }
            if caption:
                document_payload["caption"] = caption

            send_response = await client.post(
                message_url,
                headers={**authorization, "Content-Type": "application/json"},
                json={
                    "messaging_product": "whatsapp",
                    "to": destino,
                    "type": "document",
                    "document": document_payload,
                },
            )
    except httpx.RequestError as exc:
        logger.error(
            "Falha de rede ao enviar documento pelo WhatsApp: tipo=%s",
            type(exc).__name__,
        )
        return False
    except Exception as exc:
        logger.error(
            "Falha inesperada ao enviar documento pelo WhatsApp: tipo=%s",
            type(exc).__name__,
        )
        return False

    logger.info(
        "Envio de documento pela Meta: status HTTP=%s corpo=%s",
        send_response.status_code,
        send_response.text,
    )
    return not send_response.is_error
