import os

from fastapi import APIRouter, Request, Response
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

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
async def receber_mensagem(request: Request):
    dados = await request.json()

    print("\n===== MENSAGEM RECEBIDA DO WHATSAPP =====")
    print(dados)
    print("=========================================\n")

    return {"status": "ok"}