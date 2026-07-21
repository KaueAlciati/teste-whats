from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch

from backend.core.financial_agent import FinancialIntentResult, interpret_financial_message, resolve_pending_financial_message
from backend.core.models import AgentResponse, IncomingMessage
from backend.core.router import route_incoming_message
from backend.core.sessions import session_store


def _msg(text: str, channel: str = "telegram", user_id: str = "telegram:123") -> IncomingMessage:
    return IncomingMessage(user_id=user_id, channel=channel, message_type="text", text=text)


class FinancialAgentTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        session_store.clear()

    async def asyncTearDown(self) -> None:
        session_store.clear()

    async def test_relatorio_do_mes_vai_para_pdf_imediato(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            session = session_store.get("telegram", "telegram:123")
            result = await interpret_financial_message(_msg("relatorio do mes"), session)

        self.assertEqual(result.domain, "financial")
        self.assertEqual(result.intent, "generate_financial_pdf")
        self.assertEqual(result.parameters["period"], "current_month")
        self.assertTrue(result.should_execute)
        self.assertFalse(result.missing_fields)

    async def test_relatorio_sem_periodo_pede_uma_so_pergunta(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            session = session_store.get("telegram", "telegram:123")
            result = await interpret_financial_message(_msg("quero meu relatorio"), session)

        self.assertEqual(result.intent, "generate_financial_pdf")
        self.assertFalse(result.should_execute)
        self.assertEqual(result.missing_fields, ["period"])
        self.assertIsNotNone(result.clarification_question)

    async def test_gasto_natural_com_pix(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            session = session_store.get("telegram", "telegram:123")
            result = await interpret_financial_message(_msg("gastei 35 no almoço no pix"), session)

        self.assertEqual(result.intent, "register_expense")
        self.assertEqual(result.parameters["amount"], 35.0)
        self.assertIn("almoco", result.parameters["description"])
        self.assertEqual(result.parameters["payment_method"], "pix")
        self.assertTrue(result.should_execute)

    async def test_total_gasto_com_periodo_atual(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            session = session_store.get("telegram", "telegram:123")
            result = await interpret_financial_message(_msg("qto eu gastei esse mes?"), session)

        self.assertEqual(result.intent, "get_total_expense")
        self.assertEqual(result.parameters["period"], "current_month")

    async def test_lista_despesas(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            session = session_store.get("telegram", "telegram:123")
            result = await interpret_financial_message(_msg("me mostra minhas despesas"), session)

        self.assertEqual(result.intent, "list_expenses")

    async def test_pending_pdf_resolve_primeira_resposta(self) -> None:
        session = session_store.get("telegram", "telegram:123")
        session.state["pending_intent"] = "generate_financial_pdf"
        session.state["pending_parameters"] = {"format": "pdf"}
        session.state["pending_missing_fields"] = ["period"]
        session.state["pending_clarification_question"] = "Você quer o relatório deste mês ou de outro período?"

        resolution = resolve_pending_financial_message(session, "desse mes", "desse mes")
        self.assertIsNotNone(resolution)
        self.assertEqual(resolution.parameters["period"], "current_month")
        self.assertTrue(resolution.should_execute)
        self.assertFalse(resolution.missing_fields)

    async def test_router_usa_o_mesmo_nucleo_financeiro(self) -> None:
        expected = FinancialIntentResult(
            domain="financial",
            intent="generate_financial_pdf",
            confidence=0.99,
            parameters={"period": "current_month", "format": "pdf"},
            missing_fields=[],
            should_execute=True,
        )

        with patch("backend.core.router.verificar_autorizacao", return_value=True), patch(
            "backend.core.router.interpret_financial_message",
            new=AsyncMock(return_value=expected),
        ), patch(
            "backend.core.router.executar_intencao_financeira",
            new=AsyncMock(return_value=AgentResponse(text="pdf ok", response_type="document", document_name="relatorio.pdf")),
        ):
            resposta = await route_incoming_message(_msg("relatorio do mes"), session_store.get("telegram", "telegram:123"))

        self.assertEqual(resposta.response_type, "document")
        self.assertEqual(resposta.document_name, "relatorio.pdf")


if __name__ == "__main__":
    unittest.main()
