from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from backend.core.agent import process_agent_message
from backend.core.models import AgentResponse, IncomingMessage
from backend.core.router import route_incoming_message
from backend.core.sessions import session_store


class HumanizedConversationTest(unittest.TestCase):
    def setUp(self) -> None:
        session_store.clear()

    def tearDown(self) -> None:
        session_store.clear()

    def test_oi_routes_to_ai(self):
        msg = IncomingMessage(user_id="123", channel="telegram", message_type="text", text="oi")

        async def runner():
            with patch("backend.core.router.verificar_autorizacao", return_value=True), patch(
                "backend.core.router.gerar_resposta_conversacional",
                new=AsyncMock(return_value=AgentResponse(text="Oi! Tudo certo? Me conta no que você precisa de ajuda.")),
            ) as ai_mock:
                response = await route_incoming_message(msg, session_store.get("telegram", "123"))
                self.assertNotIn("Comando não reconhecido", response.text or "")
                self.assertIn("Tudo certo", response.text or "")
                ai_mock.assert_awaited_once()

        asyncio.run(runner())

    def test_ajuda_continua_funcionando(self):
        msg = IncomingMessage(user_id="123", channel="telegram", message_type="text", text="ajuda")

        async def runner():
            with patch("backend.core.router.verificar_autorizacao", return_value=True), patch(
                "backend.core.router.gerar_resposta_conversacional",
                new=AsyncMock(),
            ) as ai_mock:
                response = await route_incoming_message(msg, session_store.get("telegram", "123"))
                self.assertIn("Financeiro", response.text or "")
                self.assertIn("Gráfica", response.text or "")
                ai_mock.assert_not_awaited()

        asyncio.run(runner())

    def test_intencao_financeira_natural_usa_funcao_real(self):
        msg = IncomingMessage(user_id="5511999999999", channel="whatsapp", message_type="text", text="quanto eu gastei esse mês?")

        async def runner():
            with patch("backend.core.router.verificar_autorizacao", return_value=True), patch(
                "backend.core.router.obter_schema_por_telefone",
                return_value="schema_fin",
            ), patch("backend.core.router.calcular_total_gasto", return_value=123.45) as total_mock:
                response = await route_incoming_message(msg, session_store.get("whatsapp", "5511999999999"))
                self.assertIn("123.45", response.text or "")
                total_mock.assert_called_once_with("schema_fin")

        asyncio.run(runner())

    def test_orcamento_de_adesivo_vai_para_fluxo_da_grafica(self):
        msg = IncomingMessage(user_id="123", channel="telegram", message_type="text", text="quero fazer um orçamento de adesivo")

        async def runner():
            with patch("backend.core.router.verificar_autorizacao", return_value=True):
                response = await route_incoming_message(msg, session_store.get("telegram", "123"))
                self.assertIn("medida", (response.text or "").lower())

        asyncio.run(runner())

    def test_reset_limpa_sessao(self):
        session = session_store.get("telegram", "123")
        session.state["history"] = [{"role": "user", "content": "oi"}]
        session.state["current_intent"] = "conversational_ai"
        session_store.clear_history("telegram", "123")
        session_store.reset("telegram", "123")
        nova = session_store.get("telegram", "123")
        self.assertNotIn("history", nova.state)
        self.assertNotIn("current_intent", nova.state)

    def test_salvar_historico_falha_nao_derruba(self):
        msg = IncomingMessage(user_id="123", channel="telegram", message_type="text", text="oi")

        async def runner():
            with patch("backend.core.agent.carregar_historico_conversa", return_value=[]), patch(
                "backend.services.conversation_service.conectar_bd",
                side_effect=Exception("db down"),
            ), patch(
                "backend.core.agent.route_incoming_message",
                new=AsyncMock(return_value=AgentResponse(text="ok")),
            ):
                response = await process_agent_message(msg)
                self.assertEqual(response.text, "ok")

        asyncio.run(runner())

    def test_mesmo_nucleo_para_canais_diferentes(self):
        async def runner():
            with patch("backend.core.agent.carregar_historico_conversa", return_value=[]), patch(
                "backend.core.agent.route_incoming_message",
                new=AsyncMock(side_effect=lambda message, session: AgentResponse(text=session.channel)),
            ):
                telegram = await process_agent_message(
                    IncomingMessage(user_id="1", channel="telegram", message_type="text", text="oi")
                )
                whatsapp = await process_agent_message(
                    IncomingMessage(user_id="2", channel="whatsapp", message_type="text", text="oi")
                )
                self.assertEqual(telegram.text, "telegram")
                self.assertEqual(whatsapp.text, "whatsapp")

        asyncio.run(runner())


if __name__ == "__main__":
    unittest.main()
