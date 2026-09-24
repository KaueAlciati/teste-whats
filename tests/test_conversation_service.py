import unittest
from datetime import date
from decimal import Decimal

from backend.services.conversation_service import (
    balance_response,
    clarification_response,
    format_financial_analysis,
    format_goal_progress,
    format_largest_expense,
    format_latest_transactions,
    format_period_total,
    format_top_expense_category,
    format_brl,
    format_audio_understanding,
    format_correction_clarification,
    format_correction_not_found,
    format_natural_date,
    format_transaction_correction,
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
            "✅ *Despesa registrada*\n\n"
            "💸 *R$ 40,00*\n"
            "⛽ Gasolina\n"
            "📁 Transporte\n"
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

        self.assertIn("✅ *Receita registrada*", response)
        self.assertIn("💰 *R$ 1.500,00*", response)
        self.assertIn("💼 Salário", response)
        self.assertIn("📅 Hoje", response)

    def test_balance_response_is_natural_and_exact(self) -> None:
        response = balance_response(Decimal("1240.00"), variant=1)

        self.assertEqual(
            response,
            "💰 *Seu saldo atual*\n\n*R$ 1.240,00*",
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
            "💸 *Gastos — Este mês*\n\n*R$ 620,30*",
        )

    def test_income_total_response(self) -> None:
        response = total_response(
            transaction_type="income",
            total=Decimal("3200.00"),
            period="current_month",
            variant=0,
        )

        self.assertEqual(response, "🟢 *Entradas — Este mês*\n\n*R$ 3.200,00*")

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

    def test_balance_format_is_consistent_across_variants(self) -> None:
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

        self.assertEqual(named_response, regular_response)

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

    def test_audio_understanding_includes_transcription_and_correction_hint(self) -> None:
        response = format_audio_understanding(
            "gastei 30 reais de gasolina hoje",
            "Pronto, deixei esse gasto salvo.",
            variant=1,
        )

        self.assertIn(
            '🎧 Entendi: "gastei 30 reais de gasolina hoje"',
            response,
        )
        self.assertIn("pode me avisar", response)

    def test_transaction_correction_is_human_and_exact(self) -> None:
        response = format_transaction_correction(
            transaction_type="expense",
            amount=Decimal("50.00"),
            description="diesel",
            category="Transporte",
            transaction_date=self.current_date,
            current_date=self.current_date,
            variant=0,
        )

        self.assertIn("Boa, corrigi aqui", response)
        self.assertIn("Diesel — R$ 50,00", response)

    def test_correction_messages_are_natural(self) -> None:
        self.assertIn("lançamento recente", format_correction_not_found())
        self.assertEqual(
            format_correction_clarification(),
            "O que você quer corrigir no último lançamento?",
        )

    def test_visual_formatters_use_whatsapp_markdown(self) -> None:
        largest = format_largest_expense(
            amount=Decimal("800"),
            description="teste alerta",
            transaction_date=date(2026, 9, 23),
            period_name="Setembro",
        )
        category = format_top_expense_category(
            category="Compras",
            total=Decimal("1420"),
            period_name="Setembro",
        )
        period = format_period_total(
            transaction_type="expense",
            total=Decimal("20"),
            period_name="21/09",
            transactions=[
                (date(2026, 9, 21), "chocolate", Decimal("10")),
                (date(2026, 9, 21), "gasolina", Decimal("10")),
            ],
        )

        self.assertIn("💸 *Maior gasto — Setembro*", largest)
        self.assertIn("*R$ 800,00*", largest)
        self.assertIn("📊 *Onde você mais gastou — Setembro*", category)
        self.assertIn("Total: *R$ 20,00*", period)
        self.assertIn("Chocolate", period)

    def test_latest_transactions_are_numbered_and_limited(self) -> None:
        response = format_latest_transactions(
            transactions=[
                (date(2026, 9, 23), f"gasto {index}", Decimal("10"), "expense")
                for index in range(12)
            ],
            requested_limit=10,
            transaction_type="expense",
        )

        self.assertIn("🧾 *Seus últimos 10 gastos*", response)
        self.assertIn("10. 23/09", response)
        self.assertNotIn("11. 23/09", response)

    def test_financial_analysis_uses_existing_score_and_values(self) -> None:
        response = format_financial_analysis(
            income=Decimal("2500"),
            expenses=Decimal("2420"),
            free_amount=Decimal("80"),
            committed_percentage=96.8,
            score=35,
            level="critical",
            explanation="As despesas estão muito próximas das entradas.",
            period_name="Setembro",
        )

        self.assertIn("Entradas: *R$ 2.500,00*", response)
        self.assertIn("Renda comprometida: *96,8%*", response)
        self.assertIn("35/100 — Crítica", response)

    def test_goal_progress_bar_has_ten_positions_and_clamps(self) -> None:
        response = format_goal_progress(
            name="teste",
            current_amount=Decimal("200"),
            target_amount=Decimal("1000"),
            progress=Decimal("120"),
        )

        self.assertIn("`██████████` 100%", response)
        self.assertIn("Falta: *R$ 800,00*", response)


if __name__ == "__main__":
    unittest.main()
