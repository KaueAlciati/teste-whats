from __future__ import annotations

import logging
import os
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from backend.core.agent import process_agent_message
from backend.core.models import IncomingMessage
from backend.core.sessions import session_store

logger = logging.getLogger(__name__)


class TelegramChannelRuntime:
    def __init__(self) -> None:
        self.application: Optional[Application] = None
        self._started = False

    @property
    def enabled(self) -> bool:
        return bool(os.getenv("TELEGRAM_BOT_TOKEN"))

    async def start(self) -> None:
        if self._started:
            return

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.info("Telegram desativado por falta de token.")
            return

        self.application = Application.builder().token(token).build()
        self.application.add_handler(CommandHandler("start", self._start))
        self.application.add_handler(CommandHandler("reset", self._reset))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)
        self._started = True
        logger.info("Telegram iniciado.")

    async def stop(self) -> None:
        if not self.application or not self._started:
            return
        try:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        finally:
            self._started = False
            logger.info("Telegram desligado.")

    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        session_store.get("telegram", user_id)
        await update.message.reply_text("Bot iniciado. Envie uma mensagem para testar o agente.")

    async def _reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        session_store.reset("telegram", user_id)
        await update.message.reply_text("Sessão resetada.")
        logger.info("Sessão resetada para telegram:%s", user_id)

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = str(update.effective_user.id)
        message = IncomingMessage(
            user_id=user_id,
            channel="telegram",
            message_type="text",
            text=update.message.text,
            raw_payload=update.to_dict(),
            metadata={"display_name": update.effective_user.full_name},
        )
        logger.info("Mensagem texto recebida no Telegram: telegram:%s", user_id)
        response = await process_agent_message(message)
        await update.message.reply_text(response.text or "")
