from __future__ import annotations

import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.core.intent_classifier import IntentResult, classify_intent
from backend.core.models import IncomingMessage
from backend.core.router import route_incoming_message
from backend.core.sessions import session_store


def _msg(text: str, channel: str = "telegram", user_id: str = "123") -> IncomingMessage:
    return IncomingMessage(user_id=user_id, channel=channel, message_type="text", text=text)


class HumanizedConversationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        session_store.clear()

    async def asyncTearDown(self) -> None:
        session_store.clear()

    async def test_classifier_pdf_request(self):
        fake_json = {
            "intent": "generate_financial_pdf",
            "confidence": 0.96,
            "parameters": {"period": None, "format": "pdf"},
            "missing_fields": ["period"],
            "should_execute": False,
            "clarification_question": "Você quer o relatório deste mês ou de outro período?",
        }
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(fake_json)))]
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=completion)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await classify_intent(_msg("me gere um pdf das minha conta"), {})

        self.assertEqual(result.intent, "generate_financial_pdf")
        self.assertEqual(result.missing_fields, ["period"])
        self.assertFalse(result.should_execute)

    async def test_classifier_total_expense(self):
        fake_json = {
            "intent": "get_total_expense",
            "confidence": 0.95,
            "parameters": {"period": "current_month"},
            "missing_fields": [],
            "should_execute": True,
            "clarification_question": None,
        }
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(fake_json)))]
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=completion)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await classify_intent(_msg("quanto gastei esse mes"), {})

        self.assertEqual(result.intent, "get_total_expense")
        self.assertEqual(result.parameters["period"], "current_month")

    async def test_classifier_register_expense(self):
        fake_json = {
            "intent": "register_expense",
            "confidence": 0.97,
            "parameters": {
                "value": 35,
                "description": "gastei 35 no almoço no pix",
                "payment_method": "pix",
            },
            "missing_fields": [],
            "should_execute": True,
            "clarification_question": None,
        }
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(fake_json)))]
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=completion)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await classify_intent(_msg("gastei 35 no almoço no pix"), {})

        self.assertEqual(result.intent, "register_expense")
        self.assertEqual(result.parameters["value"], 35)
        self.assertEqual(result.parameters["payment_method"], "pix")

    async def test_classifier_graphic_quote(self):
        fake_json = {
            "intent": "graphic_quote",
            "confidence": 0.96,
            "parameters": {"product": "placa"},
            "missing_fields": ["measurement"],
            "should_execute": False,
            "clarification_question": "Certo. Qual seria a medida aproximada?",
        }
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(fake_json)))]
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=completion)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await classify_intent(_msg("quero uma placa pra minha loja"), {})

        self.assertEqual(result.intent, "graphic_quote")
        self.assertEqual(result.missing_fields, ["measurement"])

    async def test_classifier_exchange_rate(self):
        fake_json = {
            "intent": "get_exchange_rate",
            "confidence": 0.94,
            "parameters": {"currency": "USD"},
            "missing_fields": [],
            "should_execute": True,
            "clarification_question": None,
        }
        completion = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(fake_json)))]
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=completion)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await classify_intent(_msg("qual dolar hj"), {})

        self.assertEqual(result.intent, "get_exchange_rate")
        self.assertEqual(result.parameters["currency"], "USD")

    async def test_pending_pdf_flow(self):
        first = IntentResult(
            intent="generate_financial_pdf",
            confidence=0.9,
            parameters={"format": "pdf"},
            missing_fields=["period"],
            should_execute=False,
            clarification_question="Você quer o relatório deste mês ou de outro período?",
        )
        second = IntentResult(
            intent="generate_financial_pdf",
            confidence=0.98,
            parameters={"format": "pdf", "period": "current_month"},
            missing_fields=[],
            should_execute=True,
            clarification_question=None,
        )

        with patch("backend.core.router.verificar_autorizacao", return_value=True), patch(
            "backend.core.router.classify_intent",
            new=AsyncMock(side_effect=[first, second]),
        ), patch("backend.core.router.obter_schema_por_telefone", return_value="schema_fin"), patch(
            "backend.core.router.gerar_pdf_financeiro",
            return_value={"path": "/tmp/relatorio.pdf", "name": "relatorio.pdf", "period_label": "07/2026", "total": "123.45"},
        ):
            resposta1 = await route_incoming_message(_msg("quero pdf das contas"), session_store.get("telegram", "123"))
            self.assertIn("relatório deste mês", resposta1.text or "")
            self.assertEqual(session_store.get("telegram", "123").state.get("pending_intent"), "generate_financial_pdf")

            resposta2 = await route_incoming_message(_msg("desse mês"), session_store.get("telegram", "123"))
            self.assertEqual(resposta2.response_type, "document")
            self.assertEqual(resposta2.document_name, "relatorio.pdf")
            self.assertIsNotNone(resposta2.document_path)
            self.assertIsNone(session_store.get("telegram", "123").state.get("pending_intent"))

    async def test_register_expense_vai_para_funcao_real(self):
        result = IntentResult(
            intent="register_expense",
            confidence=0.99,
            parameters={"value": 35, "description": "almoço", "payment_method": "pix"},
            missing_fields=[],
            should_execute=True,
            clarification_question=None,
        )

        with patch("backend.core.router.verificar_autorizacao", return_value=True), patch(
            "backend.core.router.obter_schema_por_telefone",
            return_value="schema_fin",
        ), patch("backend.core.router.classify_intent", new=AsyncMock(return_value=result)), patch(
            "backend.core.router.salvar_gasto",
        ) as salvar_gasto_mock:
            resposta = await route_incoming_message(_msg("gastei 35 no almoço no pix"), session_store.get("whatsapp", "5511999999999"))

        self.assertIn("Registrei R$ 35.00", resposta.text or "")
        salvar_gasto_mock.assert_called_once()

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


if __name__ == "__main__":
    unittest.main()
