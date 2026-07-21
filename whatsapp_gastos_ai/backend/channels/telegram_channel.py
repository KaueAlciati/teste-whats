from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from backend.core.agent import process_agent_message
from backend.core.models import IncomingMessage
from backend.core.sessions import session_store
from backend.services.conversation_service import limpar_historico_conversa
from backend.services.web_auth_service import link_channel_by_code, resolve_channel_link

logger = logging.getLogger(__name__)

BLOCKED_TEXT = (
    "Seu Telegram ainda não está vinculado a uma conta da Fincontrol.\n\n"
    "Crie uma conta ou acesse o painel e gere um código de vinculação.\n\n"
    "Depois envie:\n"
    "/vincular SEU_CÓDIGO"
)


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
        self.application.add_handler(CommandHandler("vincular", self._link))
        self.application.add_handler(CommandHandler("ajuda_vinculo", self._help_link))
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
        telegram_user_id = str(update.effective_user.id)
        channel_user_id = f"telegram:{telegram_user_id}"
        linked = resolve_channel_link("telegram", channel_user_id)
        if linked:
            session_store.get("telegram", str(linked["user_id"]))
            await update.message.reply_text(
                f"Oi! Eu sou o assistente virtual da Fincontrol. Sua conta já está vinculada, {linked['user'].display_name}. Pode falar comigo normalmente."
            )
            return
        await update.message.reply_text(
            "Oi! Eu sou o assistente virtual da Fincontrol.\n\n"
            "Antes de conversar, vincule sua conta pelo painel e depois envie:\n"
            "/vincular SEU_CÓDIGO"
        )

    async def _help_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Para vincular seu Telegram:\n"
            "1. Abra o painel web\n"
            "2. Vá em Configurações\n"
            "3. Gere um código\n"
            "4. Envie no bot: /vincular SEU_CÓDIGO"
        )

    async def _reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        telegram_user_id = str(update.effective_user.id)
        channel_user_id = f"telegram:{telegram_user_id}"
        linked = resolve_channel_link("telegram", channel_user_id)
        session_user_id = str(linked["user_id"]) if linked else channel_user_id
        session_store.reset("telegram", session_user_id)
        session_store.clear_history("telegram", session_user_id)
        limpar_historico_conversa(session_user_id, "telegram")
        await update.message.reply_text("Sessão resetada.")
        logger.info("Sessão resetada para %s", session_user_id)

    async def _link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        telegram_user_id = str(update.effective_user.id)
        channel_user_id = f"telegram:{telegram_user_id}"
        linked = resolve_channel_link("telegram", channel_user_id)
        if linked:
            await update.message.reply_text("Seu Telegram já está vinculado à sua conta.")
            return
        if not context.args:
            await update.message.reply_text("Envie o código assim: /vincular 123456")
            return

        code = context.args[0].strip()
        try:
            result = link_channel_by_code(
                "telegram",
                channel_user_id,
                code,
                username=update.effective_user.username,
                display_name=update.effective_user.full_name,
            )
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        except Exception:
            logger.exception("Falha ao vincular Telegram: %s", channel_user_id)
            await update.message.reply_text("Não foi possível vincular agora.")
            return

        session_store.get("telegram", str(result["user_id"]))
        await update.message.reply_text("Pronto, seu Telegram foi vinculado à sua conta da Fincontrol.")
        logger.info("Telegram vinculado para %s -> user_id=%s", channel_user_id, result["user_id"])

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        telegram_user_id = str(update.effective_user.id)
        channel_user_id = f"telegram:{telegram_user_id}"
        linked = resolve_channel_link("telegram", channel_user_id)
        if not linked:
            await update.message.reply_text(BLOCKED_TEXT)
            return

        user_id = str(linked["user_id"])
        message = IncomingMessage(
            user_id=user_id,
            channel="telegram",
            message_type="text",
            text=update.message.text,
            channel_user_id=channel_user_id,
            raw_payload=update.to_dict(),
            metadata={
                "display_name": update.effective_user.full_name,
                "telegram_username": update.effective_user.username,
                "channel_user_id": channel_user_id,
            },
        )
        logger.info("Mensagem texto recebida no Telegram: %s -> user_id=%s", channel_user_id, user_id)
        response = await process_agent_message(message)
        if response.response_type == "document" and response.document_path:
            document_path = Path(response.document_path)
            try:
                with document_path.open("rb") as document:
                    await update.message.reply_document(
                        document=document,
                        filename=response.document_name or document_path.name,
                        caption=response.text or None,
                    )
            except Exception:
                logger.exception("Erro ao enviar documento no Telegram: %s", channel_user_id)
                await update.message.reply_text(response.text or "Não consegui enviar o documento agora.")
            finally:
                try:
                    document_path.unlink(missing_ok=True)
                except Exception:
                    logger.exception("Falha ao remover PDF temporário: %s", document_path)
            return
        await update.message.reply_text(response.text or "")
