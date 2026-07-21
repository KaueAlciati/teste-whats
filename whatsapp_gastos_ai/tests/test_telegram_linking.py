from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.channels.telegram_channel import TelegramChannelRuntime
from backend.core.sessions import session_store


class TelegramLinkingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        session_store.clear()

    async def asyncTearDown(self) -> None:
        session_store.clear()

    async def test_unlinked_message_is_blocked(self) -> None:
        runtime = TelegramChannelRuntime()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=123, username="user", full_name="Usuário Teste"),
            message=SimpleNamespace(reply_text=AsyncMock()),
            to_dict=lambda: {},
        )
        context = SimpleNamespace()

        with patch("backend.channels.telegram_channel.resolve_channel_link", return_value=None), patch(
            "backend.channels.telegram_channel.process_agent_message",
            new=AsyncMock(),
        ):
            await runtime._handle_text(update, context)

        update.message.reply_text.assert_awaited()
        self.assertIn("não está vinculado", update.message.reply_text.await_args.args[0].lower())

    async def test_link_command_binds_telegram(self) -> None:
        runtime = TelegramChannelRuntime()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=123, username="user", full_name="Usuário Teste"),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        context = SimpleNamespace(args=["482731"])

        with patch("backend.channels.telegram_channel.resolve_channel_link", side_effect=[None, {"user_id": 42}]), patch(
            "backend.channels.telegram_channel.link_channel_by_code",
            return_value={"user_id": 42},
        ):
            await runtime._link(update, context)

        update.message.reply_text.assert_awaited()
        self.assertIn("vinculado", update.message.reply_text.await_args.args[0].lower())


if __name__ == "__main__":
    unittest.main()
