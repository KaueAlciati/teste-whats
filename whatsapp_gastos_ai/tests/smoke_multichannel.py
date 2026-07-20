from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from backend.core.agent import process_agent_message
from backend.core.models import IncomingMessage
from backend.core.sessions import build_session_id, session_store


class SmokeMultichannelTest(unittest.TestCase):
    def test_session_prefix(self):
        self.assertEqual(build_session_id("telegram", "123"), "telegram:123")
        self.assertEqual(build_session_id("whatsapp", "5511"), "whatsapp:5511")

    def test_agent_response_mock(self):
        msg = IncomingMessage(user_id="telegram:123", channel="telegram", message_type="text", text="ajuda")

        async def runner():
            with patch("backend.core.router.route_incoming_message", new=AsyncMock(return_value=__import__("backend.core.models", fromlist=["AgentResponse"]).AgentResponse(text="ok"))):
                response = await process_agent_message(msg)
                self.assertEqual(response.text, "ok")

        asyncio.run(runner())

    def test_session_separation(self):
        telegram_session = session_store.get("telegram", "123")
        whatsapp_session = session_store.get("whatsapp", "5511")
        telegram_session.state["foo"] = "bar"
        whatsapp_session.state["foo"] = "baz"
        self.assertNotEqual(telegram_session.session_id, whatsapp_session.session_id)
        self.assertEqual(session_store.get("telegram", "123").state["foo"], "bar")
        self.assertEqual(session_store.get("whatsapp", "5511").state["foo"], "baz")


if __name__ == "__main__":
    unittest.main()
