import logging
import os

from fastapi import APIRouter, BackgroundTasks, Request, Response
from dotenv import load_dotenv

from backend.services.financial_assistant_service import (
    process_financial_audio_message,
    process_financial_message,
)
from backend.services.receipt_assistant_service import (
    process_financial_image_message,
)

load_dotenv()

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")


@router.get("/webhook")
async def verificar_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")

    return Response(content="Token inválido", status_code=403)


@router.post("/webhook")
async def receber_mensagem(request: Request, background_tasks: BackgroundTasks):
    dados = await request.json()

    for destino, message_id, texto in extrair_mensagens_de_texto(dados):
        logger.info("Mensagem de texto recebida de: %s", destino)
        background_tasks.add_task(
            process_financial_message,
            destino,
            message_id,
            texto,
        )

    for destino, message_id, media_id, mime_type in extrair_mensagens_de_audio(
        dados
    ):
        logger.info("Mensagem de áudio recebida de: %s", destino)
        background_tasks.add_task(
            process_financial_audio_message,
            destino,
            message_id,
            media_id,
            mime_type,
        )

    for (
        destino,
        message_id,
        media_id,
        mime_type,
        caption,
    ) in extrair_mensagens_de_imagem(dados):
        logger.info("Imagem recebida")
        background_tasks.add_task(
            process_financial_image_message,
            destino,
            message_id,
            media_id,
            mime_type,
            caption,
        )

    return {"status": "ok"}


def extrair_mensagens_de_texto(dados: object) -> list[tuple[str, str, str]]:
    mensagens_extraidas: list[tuple[str, str, str]] = []

    if not isinstance(dados, dict):
        return mensagens_extraidas

    entries = dados.get("entry")
    if not isinstance(entries, list):
        return mensagens_extraidas

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue

        for change in changes:
            if not isinstance(change, dict):
                continue

            value = change.get("value")
            if not isinstance(value, dict):
                continue

            metadata = value.get("metadata")
            numero_proprio = ""
            if isinstance(metadata, dict):
                numero_proprio = _somente_digitos(
                    metadata.get("display_phone_number")
                )

            messages = value.get("messages")
            if not isinstance(messages, list):
                continue

            for message in messages:
                if not isinstance(message, dict):
                    continue
                if message.get("type") != "text" or message.get("is_echo") is True:
                    continue

                destino = message.get("from")
                message_id = message.get("id")
                text = message.get("text")
                texto = text.get("body") if isinstance(text, dict) else None

                if not all(
                    isinstance(value, str)
                    for value in (destino, message_id, texto)
                ):
                    continue
                if not destino or not message_id or not texto:
                    continue
                if numero_proprio and _somente_digitos(destino) == numero_proprio:
                    continue

                mensagens_extraidas.append((destino, message_id, texto))

    return mensagens_extraidas


def extrair_mensagens_de_audio(
    dados: object,
) -> list[tuple[str, str, str, str | None]]:
    mensagens_extraidas: list[tuple[str, str, str, str | None]] = []

    if not isinstance(dados, dict):
        return mensagens_extraidas

    entries = dados.get("entry")
    if not isinstance(entries, list):
        return mensagens_extraidas

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue

        for change in changes:
            if not isinstance(change, dict):
                continue

            value = change.get("value")
            if not isinstance(value, dict):
                continue

            metadata = value.get("metadata")
            numero_proprio = ""
            if isinstance(metadata, dict):
                numero_proprio = _somente_digitos(
                    metadata.get("display_phone_number")
                )

            messages = value.get("messages")
            if not isinstance(messages, list):
                continue

            for message in messages:
                if not isinstance(message, dict):
                    continue
                if message.get("type") != "audio" or message.get("is_echo") is True:
                    continue

                destino = message.get("from")
                message_id = message.get("id")
                audio = message.get("audio")
                media_id = audio.get("id") if isinstance(audio, dict) else None
                mime_type = (
                    audio.get("mime_type") if isinstance(audio, dict) else None
                )

                if not all(
                    isinstance(item, str)
                    for item in (destino, message_id, media_id)
                ):
                    continue
                if not destino or not message_id or not media_id:
                    continue
                if mime_type is not None and not isinstance(mime_type, str):
                    mime_type = None
                if numero_proprio and _somente_digitos(destino) == numero_proprio:
                    continue

                mensagens_extraidas.append(
                    (destino, message_id, media_id, mime_type)
                )

    return mensagens_extraidas


def extrair_mensagens_de_imagem(
    dados: object,
) -> list[tuple[str, str, str, str | None, str | None]]:
    mensagens_extraidas: list[
        tuple[str, str, str, str | None, str | None]
    ] = []

    if not isinstance(dados, dict):
        return mensagens_extraidas

    entries = dados.get("entry")
    if not isinstance(entries, list):
        return mensagens_extraidas

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue

        for change in changes:
            if not isinstance(change, dict):
                continue

            value = change.get("value")
            if not isinstance(value, dict):
                continue

            metadata = value.get("metadata")
            numero_proprio = ""
            if isinstance(metadata, dict):
                numero_proprio = _somente_digitos(
                    metadata.get("display_phone_number")
                )

            messages = value.get("messages")
            if not isinstance(messages, list):
                continue

            for message in messages:
                if not isinstance(message, dict):
                    continue
                if message.get("type") != "image" or message.get("is_echo") is True:
                    continue

                destino = message.get("from")
                message_id = message.get("id")
                image = message.get("image")
                media_id = image.get("id") if isinstance(image, dict) else None
                mime_type = (
                    image.get("mime_type") if isinstance(image, dict) else None
                )
                caption = image.get("caption") if isinstance(image, dict) else None

                if not all(
                    isinstance(item, str)
                    for item in (destino, message_id, media_id)
                ):
                    continue
                if not destino or not message_id or not media_id:
                    continue
                if mime_type is not None and not isinstance(mime_type, str):
                    mime_type = None
                if caption is not None and not isinstance(caption, str):
                    caption = None
                if numero_proprio and _somente_digitos(destino) == numero_proprio:
                    continue

                mensagens_extraidas.append(
                    (destino, message_id, media_id, mime_type, caption)
                )

    return mensagens_extraidas


def _somente_digitos(valor: object) -> str:
    if not isinstance(valor, str):
        return ""
    return "".join(caractere for caractere in valor if caractere.isdigit())
