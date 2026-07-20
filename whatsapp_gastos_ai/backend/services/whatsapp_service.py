from __future__ import annotations

import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_BOT_URL = os.getenv("WHATSAPP_BOT_URL")
TOKEN = os.getenv("WHATSAPP_TOKEN") or os.getenv("TOKEN")
PHONE_ID = os.getenv("PHONE_NUMBER_ID") or os.getenv("PHONE_ID")

logger = logging.getLogger(__name__)


def _credenciais_whatsapp_disponiveis() -> bool:
    return bool(TOKEN and PHONE_ID)


async def enviar_mensagem_whatsapp(telefone, mensagem):
    if not _credenciais_whatsapp_disponiveis():
        logger.error("Credenciais do WhatsApp ausentes.")
        return False

    url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "text",
        "text": {"body": mensagem},
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return True
    except Exception:
        logger.exception("Erro ao enviar mensagem WhatsApp.")
        return False


async def enviar_menu_interativo(telefone, titulo, opcoes):
    if not _credenciais_whatsapp_disponiveis():
        return False
    buttons = [{"type": "reply", "reply": {"id": op["id"], "title": op["title"]}} for op in opcoes[:3]]
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "interactive",
        "interactive": {"type": "button", "body": {"text": titulo}, "action": {"buttons": buttons}},
    }
    url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, headers=headers, json=payload)
            return True
    except Exception:
        logger.exception("Erro ao enviar menu interativo.")
        return False


async def enviar_lista_interativa(telefone, titulo, corpo, nome_botao, secoes):
    if not _credenciais_whatsapp_disponiveis():
        return False
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "interactive",
        "interactive": {"type": "list", "header": {"type": "text", "text": titulo}, "body": {"text": corpo}, "action": {"button": nome_botao, "sections": secoes}},
    }
    url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, headers=headers, json=payload)
            return True
    except Exception:
        logger.exception("Erro ao enviar lista interativa.")
        return False


async def obter_url_midia(media_id: str) -> str | None:
    if not _credenciais_whatsapp_disponiveis():
        return None
    url = f"https://graph.facebook.com/v22.0/{media_id}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get("url")
    except Exception:
        logger.exception("Erro ao obter URL da mídia.")
        return None


async def baixar_midia(url: str, caminho_destino: str):
    if not _credenciais_whatsapp_disponiveis():
        return None
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            with open(caminho_destino, "wb") as f:
                f.write(response.content)
            return caminho_destino
    except Exception:
        logger.exception("Erro ao baixar mídia.")
        return None


async def enviar_imagem_whatsapp(telefone, caminho_imagem, caption=None):
    if not _credenciais_whatsapp_disponiveis():
        return False
    url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        upload_url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/media"
        with open(caminho_imagem, "rb") as image_file:
            files = {"file": (os.path.basename(caminho_imagem), image_file, "image/png")}
            form_data = {"messaging_product": "whatsapp", "type": "image/png"}
            async with httpx.AsyncClient() as client:
                upload_response = await client.post(upload_url, headers={"Authorization": f"Bearer {TOKEN}"}, files=files, data=form_data)
                upload_response.raise_for_status()
                media_id = upload_response.json().get("id")
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": telefone,
                    "type": "image",
                    "image": {"id": media_id, "caption": caption if caption else None},
                }
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return True
    except Exception:
        logger.exception("Erro ao enviar imagem.")
        return False
