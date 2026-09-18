import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.schemas.financial_intent import FinancialIntent
from backend.services.ai_financial_service import (
    DEFAULT_OPENAI_MODEL,
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
            {"OPENAI_API_KEY": "test-key"},
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
                    ):
                        result = interpret_financial_message(
                            message,
                            date(2026, 9, 18),
                        )

                    self.assertEqual(result, expected_intent)
                    call_arguments = client.responses.parse.call_args.kwargs
                    self.assertEqual(call_arguments["model"], DEFAULT_OPENAI_MODEL)
                    self.assertIs(call_arguments["text_format"], FinancialIntent)
                    self.assertFalse(call_arguments["store"])
                    self.assertIn(message, call_arguments["input"])

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
            {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "configured-model"},
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


if __name__ == "__main__":
    unittest.main()
