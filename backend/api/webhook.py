import logging
import os

from fastapi import APIRouter, BackgroundTasks, Request, Response
from dotenv import load_dotenv

from backend.services.user_service import register_whatsapp_user
from backend.services.whatsapp_service import send_text_message

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

    for destino, texto in extrair_mensagens_de_texto(dados):
        logger.info("Mensagem de texto recebida de: %s", destino)
        background_tasks.add_task(
            send_text_message,
            destino,
            "Olá! Seu assistente financeiro está conectado ao WhatsApp ✅",
        )
        background_tasks.add_task(register_whatsapp_user, destino)

    return {"status": "ok"}


def extrair_mensagens_de_texto(dados: object) -> list[tuple[str, str]]:
    mensagens_extraidas: list[tuple[str, str]] = []

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
                text = message.get("text")
                texto = text.get("body") if isinstance(text, dict) else None

                if not isinstance(destino, str) or not isinstance(texto, str):
                    continue
                if not destino or not texto:
                    continue
                if numero_proprio and _somente_digitos(destino) == numero_proprio:
                    continue

                mensagens_extraidas.append((destino, texto))

    return mensagens_extraidas


def _somente_digitos(valor: object) -> str:
    if not isinstance(valor, str):
        return ""
    return "".join(caractere for caractere in valor if caractere.isdigit())
