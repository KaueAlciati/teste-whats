from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.core.agent import process_agent_message
from backend.core.intent_classifier import classify_intent
from backend.core.models import AgentResponse, IncomingMessage
from backend.core.pending_intent_resolver import resolve_pending_intent
from backend.core.router import route_incoming_message
from backend.core.sessions import session_store
from backend.core.text_normalizer import normalize_user_text, remove_accents_for_matching


def _msg(text: str, channel: str = "telegram", user_id: str = "123") -> IncomingMessage:
    return IncomingMessage(user_id=user_id, channel=channel, message_type="text", text=text)


class HumanizedConversationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        session_store.clear()

    async def asyncTearDown(self) -> None:
        session_store.clear()

    def test_text_normalizer_expands_common_abbreviations(self):
        self.assertEqual(normalize_user_text("vc consegue gerar o pdf hj?"), "você consegue gerar o pdf hoje?")
        self.assertEqual(remove_accents_for_matching("desse mês"), "desse mes")

    async def test_classifier_pdf_request_with_explicit_period(self):
        result = await classify_intent(_msg("relatorio da conta desse mes"), {})
        self.assertEqual(result.intent, "generate_financial_pdf")
        self.assertEqual(result.parameters["period"], "current_month")
        self.assertFalse(result.missing_fields)
        self.assertTrue(result.should_execute)

    async def test_classifier_pdf_request_natural_language(self):
        result = await classify_intent(_msg("vc consegue gerar um pdf das minhas conta pfv"), {})
        self.assertEqual(result.intent, "generate_financial_pdf")

    async def test_classifier_total_expense_without_accents(self):
        result = await classify_intent(_msg("qto gastei esse mes"), {})
        self.assertEqual(result.intent, "get_total_expense")
        self.assertEqual(result.parameters["period"], "current_month")

    async def test_classifier_exchange_rate(self):
        result = await classify_intent(_msg("qual dolar hj"), {})
        self.assertEqual(result.intent, "get_exchange_rate")
        self.assertEqual(result.parameters["currency"], "USD")

    async def test_pending_pdf_flow_resolves_first_reply(self):
        session = session_store.get("telegram", "123")
        session.state["pending_intent"] = "generate_financial_pdf"
        session.state["pending_parameters"] = {"format": "pdf"}
        session.state["pending_missing_fields"] = ["period"]
        session.state["pending_clarification_question"] = "Voce quer o relatorio deste mes ou de outro periodo?"

        resolution = await resolve_pending_intent(session, "desse mes", "desse mes")
        self.assertTrue(resolution.matched)
        self.assertEqual(resolution.parameters["period"], "current_month")
        self.assertFalse(resolution.remaining_fields)

    async def test_pending_pdf_flow_question_then_resolution(self):
        pdf_response = AgentResponse(
            text="Pronto. Gerei o relatório financeiro de 07/2026.",
            response_type="document",
            document_path="/tmp/relatorio.pdf",
            document_name="relatorio.pdf",
            metadata={"intent": "generate_financial_pdf", "period": "07/2026", "total": "123.45"},
        )

        async def _fake_exec(message, session, result):
            if result.missing_fields:
                session.state["pending_intent"] = "generate_financial_pdf"
                session.state["pending_parameters"] = dict(result.parameters or {})
                session.state["pending_missing_fields"] = list(result.missing_fields or [])
                session.state["pending_clarification_question"] = result.clarification_question
                return AgentResponse(text=result.clarification_question or "Você quer o relatório de qual período?", metadata={"intent": "generate_financial_pdf", "pending": True})
            return pdf_response

        with patch("backend.core.router.verificar_autorizacao", return_value=True), patch(
            "backend.core.router.obter_schema_por_telefone",
            return_value="schema_fin",
        ), patch("backend.core.router.executar_intencao_financeira", new=AsyncMock(side_effect=_fake_exec)):
            session = session_store.get("telegram", "123")
            first = await route_incoming_message(_msg("quero um relatorio das minhas contas"), session)
            self.assertIn("período", (first.text or "").lower())
            self.assertEqual(session.state.get("pending_intent"), "generate_financial_pdf")

            second = await route_incoming_message(_msg("desse mes"), session)

        self.assertEqual(second.response_type, "document")
        self.assertEqual(second.document_name, "relatorio.pdf")
        self.assertIsNone(session_store.get("telegram", "123").state.get("pending_intent"))

    async def test_pending_pdf_flow_through_router(self):
        first = AgentResponse(
            text="Voce quer o relatorio deste mes ou de outro periodo?",
            metadata={"intent": "generate_financial_pdf", "pending": True},
        )
        pdf_response = AgentResponse(
            text="Pronto. Gerei o relatório financeiro de 07/2026.",
            response_type="document",
            document_path="/tmp/relatorio.pdf",
            document_name="relatorio.pdf",
            metadata={"intent": "generate_financial_pdf", "period": "07/2026", "total": "123.45"},
        )

        with patch("backend.core.router.verificar_autorizacao", return_value=True), patch(
            "backend.core.router.obter_schema_por_telefone",
            return_value="schema_fin",
        ), patch("backend.core.router.executar_intencao_financeira", new=AsyncMock(return_value=pdf_response)), patch(
            "backend.core.router.gerar_resposta_conversacional",
            new=AsyncMock(return_value=AgentResponse(text="fallback")),
        ):
            session = session_store.get("telegram", "123")
            session.state["pending_intent"] = "generate_financial_pdf"
            session.state["pending_parameters"] = {"format": "pdf"}
            session.state["pending_missing_fields"] = ["period"]
            session.state["pending_clarification_question"] = first.text
            resposta = await route_incoming_message(_msg("desse mes"), session)

        self.assertEqual(resposta.response_type, "document")
        self.assertEqual(resposta.document_name, "relatorio.pdf")
        self.assertEqual(resposta.metadata["period"], "07/2026")
        self.assertIsNone(session_store.get("telegram", "123").state.get("pending_intent"))

    async def test_graphic_quote_pending_flow_keeps_context(self):
        session = session_store.get("telegram", "123")
        session.state["pending_intent"] = "graphic_quote"
        session.state["pending_parameters"] = {"product": "adesivo"}
        session.state["pending_missing_fields"] = ["measurement"]
        session.state["pending_clarification_question"] = "Certo. Qual seria a medida aproximada?"

        resolution = await resolve_pending_intent(session, "50x20", "50x20")
        self.assertTrue(resolution.matched)
        self.assertEqual(resolution.parameters["measurement"], "50x20")
        self.assertIn("quantity", resolution.remaining_fields)

    async def test_confirmation_and_negative_periods(self):
        session = session_store.get("telegram", "123")
        session.state["pending_intent"] = "generate_financial_pdf"
        session.state["pending_parameters"] = {"format": "pdf"}
        session.state["pending_missing_fields"] = ["period"]
        session.state["pending_clarification_question"] = "Voce quer o relatorio deste mes ou de outro periodo?"

        positive = await resolve_pending_intent(session, "pode ser", "pode ser")
        self.assertEqual(positive.parameters["period"], "current_month")

        session.state["pending_intent"] = "generate_financial_pdf"
        session.state["pending_parameters"] = {"format": "pdf"}
        session.state["pending_missing_fields"] = ["period"]
        session.state["pending_clarification_question"] = "Voce quer o relatorio deste mes ou de outro periodo?"
        negative = await resolve_pending_intent(session, "nao, do mes passado", "nao do mes passado")
        self.assertEqual(negative.parameters["period"], "previous_month")

    async def test_openai_error_cai_em_fallback(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("openai down"))

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await classify_intent(_msg("oi"), {})

        self.assertEqual(result.intent, "greeting")

    async def test_oi_nao_retorna_comando_nao_reconhecido(self):
        with patch("backend.core.router.verificar_autorizacao", return_value=True):
            resposta = await route_incoming_message(_msg("oi"), session_store.get("telegram", "123"))

        self.assertNotIn("Comando não reconhecido", resposta.text or "")
        self.assertIn("tudo certo", (resposta.text or "").lower())

    async def test_process_agent_message_preserva_texto_original_e_normalizado(self):
        with patch("backend.core.router.verificar_autorizacao", return_value=True), patch(
            "backend.core.router.classify_intent",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    intent="greeting",
                    confidence=1.0,
                    parameters={},
                    missing_fields=[],
                    should_execute=True,
                    clarification_question=None,
                )
            ),
        ):
            message = _msg("vc consegue gerar um pdf hj?")
            await process_agent_message(message)

        self.assertEqual(message.text_original, "vc consegue gerar um pdf hj?")
        self.assertEqual(message.text_normalized, "você consegue gerar um pdf hoje?")


if __name__ == "__main__":
    unittest.main()
