from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.channels.telegram_channel import TelegramChannelRuntime
from backend.channels.whatsapp_channel import build_incoming_message_from_meta, handle_incoming_whatsapp_message
from backend.services.db_init import inicializar_bd
from backend.utils import mensagem_ja_processada, registrar_mensagem_recebida

load_dotenv()

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "app.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
telegram_runtime = TelegramChannelRuntime()

if DATABASE_URL:
    inicializar_bd(DATABASE_URL)
else:
    logger.warning("DATABASE_URL não configurada; inicialização do banco ignorada.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if telegram_runtime.enabled:
        await telegram_runtime.start()
    else:
        logger.info("Telegram desativado por falta de TELEGRAM_BOT_TOKEN.")
    try:
        yield
    finally:
        await telegram_runtime.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/ping")
def ping():
    return {"status": "alive!"}


@app.get("/debug")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(content=params["hub.challenge"])
    return {"status": "erro", "mensagem": "Token inválido."}


@app.post("/debug")
async def debug_route(request: Request):
    data = await request.json()
    logger.info("DEBUG /debug: %s", json.dumps(data, ensure_ascii=False))
    return {"status": "ok", "received_data": data}


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(content=params["hub.challenge"])
    return {"status": "erro", "mensagem": "Token inválido."}


@app.post("/webhook")
async def receber_mensagem(request: Request):
    inicio = time.time()
    logger.info("Recebi algo no webhook.")

    try:
        dados = await request.json()
        logger.info("Payload recebido: %s", json.dumps(dados, indent=2, ensure_ascii=False))
    except Exception as exc:
        body = await request.body()
        logger.exception("Erro ao decodificar JSON: %s", exc)
        return JSONResponse(content={"status": "erro", "mensagem": "Payload inválido."}, status_code=400)

    message = build_incoming_message_from_meta(dados)
    if not message:
        return JSONResponse(content={"status": "ignorado", "mensagem": "Nenhuma mensagem nova."}, status_code=200)

    mensagem_id = message.metadata.get("message_id")
    if mensagem_id and mensagem_ja_processada(mensagem_id):
        logger.warning("Mensagem duplicada ignorada: %s", mensagem_id)
        return JSONResponse(content={"status": "ignorado", "mensagem": "Mensagem duplicada ignorada."}, status_code=200)

    if mensagem_id:
        registrar_mensagem_recebida(mensagem_id, message.user_id, message.message_type)

    await handle_incoming_whatsapp_message(dados)

    logger.info("Webhook processado em %.2fs", time.time() - inicio)
    return JSONResponse(content={"status": "ok"}, status_code=200)
