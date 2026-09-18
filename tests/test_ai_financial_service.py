import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx2
from openai import APIStatusError
from openai.lib._pydantic import to_strict_json_schema

from backend.schemas.financial_intent import FinancialIntent
from backend.services.ai_financial_service import (
    DEFAULT_AI_MODEL,
    GROQ_BASE_URL,
    FinancialAIServiceError,
    interpret_financial_message,
)


class AIFinancialServiceTestCase(unittest.TestCase):
    def test_interprets_supported_examples_with_structured_outputs(self) -> None:
        cases = (
            (
                "gastei 40 reais de gasolina",
                FinancialIntent(
                    action="create_expense",
                    amount=40,
                    description="gasolina",
                    category="Transporte",
                    transaction_date="2026-09-18",
                    payment_method=None,
                    period=None,
                    needs_clarification=False,
                    clarification_question=None,
                    confidence=0.98,
                ),
            ),
            (
                "recebi 1500 de salário",
                FinancialIntent(
                    action="create_income",
                    amount=1500,
                    description="salário",
                    category="Salário",
                    transaction_date="2026-09-18",
                    payment_method=None,
                    period=None,
                    needs_clarification=False,
                    clarification_question=None,
                    confidence=0.99,
                ),
            ),
            (
                "quanto eu tenho?",
                FinancialIntent(
                    action="query_balance",
                    amount=None,
                    description=None,
                    category=None,
                    transaction_date=None,
                    payment_method=None,
                    period="all",
                    needs_clarification=False,
                    clarification_question=None,
                    confidence=0.99,
                ),
            ),
            (
                "quanto gastei esse mês?",
                FinancialIntent(
                    action="query_expenses",
                    amount=None,
                    description=None,
                    category=None,
                    transaction_date=None,
                    payment_method=None,
                    period="current_month",
                    needs_clarification=False,
                    clarification_question=None,
                    confidence=0.99,
                ),
            ),
        )

        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": "test-key", "AI_PROVIDER": "groq"},
            clear=True,
        ):
            for message, expected_intent in cases:
                with self.subTest(message=message):
                    client = Mock()
                    client.responses.parse.return_value = SimpleNamespace(
                        output_parsed=expected_intent
                    )
                    with patch(
                        "backend.services.ai_financial_service.OpenAI",
                        return_value=client,
                    ) as openai_client:
                        result = interpret_financial_message(
                            message,
                            date(2026, 9, 18),
                        )

                    self.assertEqual(result, expected_intent)
                    openai_client.assert_called_once_with(
                        api_key="test-key",
                        base_url=GROQ_BASE_URL,
                        timeout=20.0,
                        max_retries=1,
                    )
                    call_arguments = client.responses.parse.call_args.kwargs
                    self.assertEqual(call_arguments["model"], DEFAULT_AI_MODEL)
                    self.assertIs(call_arguments["text_format"], FinancialIntent)
                    self.assertNotIn("store", call_arguments)
                    self.assertIn(message, call_arguments["input"])
                    self.assertIn(
                        "objeto ou motivo curto",
                        call_arguments["instructions"],
                    )

    def test_uses_configured_model(self) -> None:
        intent = FinancialIntent(
            action="unknown",
            amount=None,
            description=None,
            category=None,
            transaction_date=None,
            payment_method=None,
            period=None,
            needs_clarification=False,
            clarification_question=None,
            confidence=0.7,
        )
        client = Mock()
        client.responses.parse.return_value = SimpleNamespace(output_parsed=intent)

        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "test-key",
                "AI_PROVIDER": "groq",
                "AI_MODEL": "configured-model",
            },
            clear=True,
        ):
            with patch(
                "backend.services.ai_financial_service.OpenAI",
                return_value=client,
            ):
                interpret_financial_message("olá", date(2026, 9, 18))

        self.assertEqual(
            client.responses.parse.call_args.kwargs["model"],
            "configured-model",
        )

    def test_missing_api_key_raises_safe_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(FinancialAIServiceError):
                interpret_financial_message("gastei 10", date(2026, 9, 18))

    def test_financial_intent_is_compatible_with_strict_output(self) -> None:
        schema = to_strict_json_schema(FinancialIntent)

        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            set(schema["properties"]),
        )

        nullable_fields = (
            "amount",
            "description",
            "category",
            "transaction_date",
            "payment_method",
            "period",
            "clarification_question",
        )
        for field_name in nullable_fields:
            with self.subTest(field_name=field_name):
                field_types = {
                    option.get("type")
                    for option in schema["properties"][field_name]["anyOf"]
                }
                self.assertIn("null", field_types)

    def test_logs_safe_groq_configuration(self) -> None:
        intent = FinancialIntent(
            action="query_balance",
            amount=None,
            description=None,
            category=None,
            transaction_date=None,
            payment_method=None,
            period="all",
            needs_clarification=False,
            clarification_question=None,
            confidence=0.99,
        )
        client = Mock()
        client.responses.parse.return_value = SimpleNamespace(output_parsed=intent)

        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "test-secret-key",
                "AI_PROVIDER": "groq",
                "AI_MODEL": DEFAULT_AI_MODEL,
            },
            clear=True,
        ):
            with (
                patch(
                    "backend.services.ai_financial_service.OpenAI",
                    return_value=client,
                ),
                patch("backend.services.ai_financial_service.logger") as logger,
            ):
                interpret_financial_message("quanto eu tenho?", date(2026, 9, 18))

        logger.info.assert_any_call("AI_PROVIDER: %s", "groq")
        logger.info.assert_any_call("AI_MODEL: %s", DEFAULT_AI_MODEL)
        logger.info.assert_any_call("GROQ_API_KEY configurada: %s", True)
        self.assertNotIn("test-secret-key", str(logger.mock_calls))

    def test_api_status_error_is_wrapped_and_logged_safely(self) -> None:
        request = httpx2.Request("POST", f"{GROQ_BASE_URL}/responses")
        response = httpx2.Response(429, request=request)
        api_error = APIStatusError(
            "rate limit",
            response=response,
            body={"error": "rate limit"},
        )
        client = Mock()
        client.responses.parse.side_effect = api_error

        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": "test-secret-key", "AI_PROVIDER": "groq"},
            clear=True,
        ):
            with (
                patch(
                    "backend.services.ai_financial_service.OpenAI",
                    return_value=client,
                ),
                patch("backend.services.ai_financial_service.logger") as logger,
            ):
                with self.assertRaises(FinancialAIServiceError):
                    interpret_financial_message("gastei 10", date(2026, 9, 18))

        logger.error.assert_called_once_with(
            "Erro da Groq: status HTTP=%s; tipo=%s",
            429,
            "APIStatusError",
        )
        self.assertNotIn("test-secret-key", str(logger.mock_calls))


if __name__ == "__main__":
    unittest.main()
