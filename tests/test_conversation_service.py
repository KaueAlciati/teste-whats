import unittest
from datetime import date
from decimal import Decimal

from backend.services.conversation_service import (
    balance_response,
    clarification_response,
    format_brl,
    format_natural_date,
    non_financial_response,
    response_variant,
    total_response,
    transaction_confirmation,
)


class ConversationServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.current_date = date(2026, 9, 18)

    def test_human_expense_response_uses_validated_data(self) -> None:
        response = transaction_confirmation(
            transaction_type="expense",
            amount=Decimal("40.00"),
            description="gasolina",
            category="Transporte",
            transaction_date=self.current_date,
            current_date=self.current_date,
            variant=0,
        )

        self.assertEqual(
            response,
            "Beleza, já registrei pra você 👌\n\n"
            "⛽ Gasolina — R$ 40,00\n"
            "📂 Transporte\n"
            "📅 Hoje",
        )

    def test_human_income_response_uses_validated_data(self) -> None:
        response = transaction_confirmation(
            transaction_type="income",
            amount=Decimal("1500.00"),
            description="salário",
            category="Salário",
            transaction_date=self.current_date,
            current_date=self.current_date,
            variant=0,
        )

        self.assertIn("Boa! Já registrei essa entrada", response)
        self.assertIn("💼 Salário — R$ 1.500,00", response)
        self.assertIn("📅 Hoje", response)

    def test_balance_response_is_natural_and_exact(self) -> None:
        response = balance_response(Decimal("1240.00"), variant=1)

        self.assertEqual(
            response,
            "Você está com R$ 1.240,00 de saldo no momento.",
        )

    def test_expense_total_response(self) -> None:
        response = total_response(
            transaction_type="expense",
            total=Decimal("620.30"),
            period="current_month",
            variant=0,
        )

        self.assertEqual(
            response,
            "Até agora você gastou R$ 620,30 neste mês.",
        )

    def test_income_total_response(self) -> None:
        response = total_response(
            transaction_type="income",
            total=Decimal("3200.00"),
            period="current_month",
            variant=0,
        )

        self.assertEqual(response, "Neste mês entraram R$ 3.200,00.")

    def test_clarification_preserves_natural_question(self) -> None:
        response = clarification_response(
            action="create_expense",
            question="Quanto você gastou no mercado?",
            missing_amount=True,
            missing_description=False,
        )

        self.assertEqual(response, "Quanto você gastou no mercado?")

    def test_clarification_replaces_technical_question(self) -> None:
        response = clarification_response(
            action="create_income",
            question="amount is required",
            missing_amount=True,
            missing_description=False,
        )

        self.assertEqual(response, "Quanto você recebeu?")

    def test_greeting_is_simple_and_financial(self) -> None:
        response = non_financial_response("bom dia", variant=0)

        self.assertEqual(
            response,
            "Bom dia! ☀️ Me conta, como posso te ajudar com suas finanças?",
        )

    def test_user_name_is_used_only_in_name_variant(self) -> None:
        named_response = balance_response(
            Decimal("100.00"),
            user_name="Kauê Alciati",
            variant=2,
        )
        regular_response = balance_response(
            Decimal("100.00"),
            user_name="Kauê Alciati",
            variant=0,
        )

        self.assertIn("Kauê", named_response)
        self.assertNotIn("Kauê", regular_response)

    def test_missing_user_name_does_not_leak_placeholder(self) -> None:
        response = non_financial_response("oi", user_name=None, variant=2)

        self.assertNotIn("None", response)
        self.assertEqual(response, "Oi! 👋 Como posso te ajudar hoje?")

    def test_brl_formatting_uses_decimal(self) -> None:
        cases = (
            (Decimal("40"), "R$ 40,00"),
            (Decimal("1500.5"), "R$ 1.500,50"),
            (Decimal("10000"), "R$ 10.000,00"),
        )

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_brl(value), expected)

        with self.assertRaises(TypeError):
            format_brl(40.0)  # type: ignore[arg-type]

    def test_natural_date_formats_today(self) -> None:
        self.assertEqual(
            format_natural_date(self.current_date, self.current_date),
            "Hoje",
        )

    def test_natural_date_formats_yesterday(self) -> None:
        self.assertEqual(
            format_natural_date(date(2026, 9, 17), self.current_date),
            "Ontem",
        )

    def test_response_variant_is_stable(self) -> None:
        self.assertEqual(
            response_variant("wamid.same-message"),
            response_variant("wamid.same-message"),
        )


if __name__ == "__main__":
    unittest.main()
