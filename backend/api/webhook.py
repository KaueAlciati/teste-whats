import logging
import os

from fastapi import APIRouter, BackgroundTasks, Request, Response
from dotenv import load_dotenv

from backend.services.financial_assistant_service import process_financial_message

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


def _somente_digitos(valor: object) -> str:
    if not isinstance(valor, str):
        return ""
    return "".join(caractere for caractere in valor if caractere.isdigit())
