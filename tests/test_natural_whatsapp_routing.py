import os
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.database.base import Base
from backend.models import (
    Category,
    FinancialProfile,
    FinancialTransaction,
    Goal,
    GoalContribution,
    IntentClarification,
    IntentExample,
    UnrecognizedMessage,
    User,
)
from backend.schemas.financial_intent import FinancialIntent
from backend.schemas.natural_intent import (
    NaturalIntentDecision,
    NaturalIntentParameters,
)
from backend.services.financial_assistant_service import handle_financial_message
from backend.services.financial_service import create_transaction
from backend.services.goal_contribution_service import add_goal_contribution
from backend.services.goal_service import create_goal
from backend.services.intent_router_service import IntentRouteOutcome
from backend.services.statement_export_service import ExportedStatement


class NaturalWhatsAppRoutingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.environment = patch.dict(os.environ, {"GROQ_API_KEY": ""})
        self.environment.start()
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.current_date = date(2026, 9, 23)
        self.current_time = datetime(
            2026,
            9,
            23,
            12,
            tzinfo=ZoneInfo("America/Sao_Paulo"),
        )
        self.user = self._user("user@example.com", "5515999999999")
        self.other_user = self._user("other@example.com", "5515888888888")
        food = Category(
            name="Alimentação",
            type="expense",
            is_default=True,
        )
        transport = Category(
            name="Transporte",
            type="expense",
            is_default=True,
        )
        purchases = Category(name="Compras", type="expense", is_default=True)
        salary = Category(name="Salário", type="income", is_default=True)
        others_expense = Category(name="Outros", type="expense", is_default=True)
        others_income = Category(name="Outros", type="income", is_default=True)
        self.session.add_all(
            [food, transport, purchases, salary, others_expense, others_income]
        )
        self.session.commit()
        self.food_id = food.id
        self.transport_id = transport.id
        self.purchases_id = purchases.id
        self.salary_id = salary.id
        self.session.add(
            FinancialProfile(
                user_id=self.user.id,
                main_goal="organize_finances",
                investment_horizon="up_to_1_year",
                risk_profile="conservative",
                liquidity_need="high",
                has_debts=False,
                income_type="fixed",
                main_priority="organize_budget",
                onboarding_completed=True,
            )
        )
        self.session.commit()
        self._transaction("income", "2000", "Salário", self.current_date, self.salary_id)
        self._transaction("expense", "80", "Gasolina", self.current_date, self.transport_id)
        self._transaction("expense", "150", "Mercado", self.current_date, self.food_id)
        self._transaction("expense", "40", "Padaria", date(2026, 9, 22), self.food_id)

    def tearDown(self) -> None:
        self.session.close()
        self.environment.stop()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_new_read_only_intents_use_real_user_data(self) -> None:
        cases = (
            ("qual minha maior despesa?", "Mercado"),
            ("com o que eu mais gastei?", "Alimentação"),
            ("quanto gastei com gasolina?", "R$ 80,00"),
            ("me mostra os últimos 3 gastos", "Padaria"),
            ("como estão minhas finanças?", "score"),
            ("o que posso melhorar?", "dados atuais"),
        )
        for index, (phrase, expected) in enumerate(cases):
            with self.subTest(phrase=phrase):
                response = self._message(phrase, f"natural-{index}")
                self.assertIn(expected, response)

    def test_period_query_uses_fallback_after_existing_intent_returns_unknown(self) -> None:
        response = self._message_with_unknown_financial_intent(
            "quanto gastei ontem?",
            "period-yesterday",
        )

        self.assertIn("R$ 40,00", response)
        self.assertIn("Ontem", response)

    def test_query_quantities_and_largest_expenses_are_deterministic(self) -> None:
        latest_expenses = self._message(
            "me mostra meus últimos 3 gastos",
            "quantity-three-expenses",
        )
        movements = self._message(
            "me mostra 10 movimentações",
            "quantity-ten-movements",
        )
        largest = self._message(
            "quais foram meus 2 maiores gastos?",
            "quantity-two-largest",
        )

        self.assertIn("Seus últimos 3 gastos", latest_expenses)
        self.assertIn("Suas últimas 10 movimentações", movements)
        self.assertIn("Seus 2 maiores gastos", largest)
        self.assertLess(largest.index("Mercado"), largest.index("Gasolina"))

    def test_category_and_period_queries_use_backend_data(self) -> None:
        self._transaction(
            "expense",
            "60",
            "Restaurante",
            date(2026, 9, 18),
            self.food_id,
        )
        self._transaction(
            "expense",
            "25",
            "Tênis",
            date(2026, 9, 22),
            self.purchases_id,
        )
        self._transaction(
            "expense",
            "50",
            "Pedágio",
            date(2026, 8, 10),
            self.transport_id,
        )
        cases = (
            ("quanto gastei com gasolina esse mês?", "R$ 80,00"),
            ("quanto gastei com alimentação semana passada?", "R$ 60,00"),
            ("quanto gastei em compras ontem?", "R$ 25,00"),
            ("quanto foi de transporte em agosto?", "R$ 50,00"),
            ("quanto gastei com mercado nos últimos 30 dias?", "R$ 150,00"),
            ("quanto gastei com alimentasao esse mês?", "R$ 250,00"),
        )
        for index, (phrase, expected) in enumerate(cases):
            with self.subTest(phrase=phrase):
                response = self._message(phrase, f"category-period-{index}")
                self.assertIn(expected, response)

    def test_unknown_category_requests_clarification(self) -> None:
        response = self._message(
            "quanto gastei com teletransporte esse mês?",
            "unknown-category",
        )

        self.assertIn("Qual categoria", response)

    def test_impossible_date_is_rejected_without_financial_ai(self) -> None:
        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message"
        ) as financial_ai:
            response = self._message(
                "quanto gastei em 31/09?",
                "invalid-explicit-date",
            )

        self.assertIn("data válida", response)
        financial_ai.assert_not_called()

    def test_extended_periods_use_backend_parser_before_financial_ai(self) -> None:
        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message"
        ) as financial_ai:
            named_month = self._message(
                "quanto gastei em setembro?",
                "period-named-month",
            )
            previous_week = self._message(
                "quanto gastei semana passada?",
                "period-previous-week",
            )

        self.assertIn("R$ 270,00", named_month)
        self.assertIn("Nenhuma despesa", previous_week)
        financial_ai.assert_not_called()

    def test_specific_day_queries_use_current_month_and_year(self) -> None:
        cases = (
            ("quanto gastei dia 21?", "R$ 0,00", "Chocolate"),
            ("quanto gastei no dia 21?", "R$ 0,00", "Gasolina"),
            ("gastos do dia 21", "R$ 0,00", "21/09"),
            ("recebi quanto dia 18?", None, "Nenhuma entrada"),
            ("quanto gastei em 21/09?", "R$ 0,00", "Chocolate"),
            ("quanto gastei em 21 de setembro?", "R$ 0,00", "Gasolina"),
        )
        self._transaction("expense", "10", "Chocolate", date(2026, 9, 21), self.food_id)
        self._transaction("expense", "10", "Gasolina", date(2026, 9, 21), self.transport_id)

        for index, (phrase, excluded, expected) in enumerate(cases):
            with self.subTest(phrase=phrase):
                response = self._message(phrase, f"specific-day-{index}")
                self.assertIn(expected, response)
                if excluded is not None:
                    self.assertNotIn(excluded, response)

    def test_audio_transcription_uses_the_same_router(self) -> None:
        response = self._message(
            "como ta minhas finança",
            "audio-natural",
            source="whatsapp_audio",
            audio_transcription="como ta minhas finança",
        )

        self.assertNotIn("Entendi:", response)
        self.assertIn("score", response)

    def test_audio_unrecognized_message_keeps_audio_source(self) -> None:
        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=self._unknown_intent(),
        ):
            self._message(
                "frase sem sentido financeiro",
                "audio-unknown",
                source="whatsapp_audio",
                audio_transcription="frase sem sentido financeiro",
            )

        record = self.session.scalar(
            select(UnrecognizedMessage).where(
                UnrecognizedMessage.user_id == self.user.id,
                UnrecognizedMessage.message == "frase sem sentido financeiro",
            )
        )
        self.assertEqual(record.source, "whatsapp_audio")

    def test_goal_queries_and_natural_goal_statement(self) -> None:
        goal = create_goal(
            self.session,
            user_id=self.user.id,
            name="Teste",
            target_amount=Decimal("100.00"),
            target_date=None,
        )
        add_goal_contribution(
            self.session,
            goal_id=goal.id,
            user_id=self.user.id,
            amount="70.00",
            source="whatsapp_text",
        )

        closest = self._message("qual meta falta menos", "goal-closest")
        status = self._message("como estão minhas metas?", "goal-status")
        statement = self._message("extrato do test", "goal-statement")

        self.assertIn("Teste", closest)
        self.assertIn("70%", status)
        self.assertIn("R$ 70,00", statement)

    def test_natural_goal_contribution_keeps_existing_write_flow(self) -> None:
        goal = create_goal(
            self.session,
            user_id=self.user.id,
            name="Teste",
            target_amount=Decimal("500.00"),
            target_date=None,
        )

        response = self._message("coloca 50 no teste", "goal-natural-add")

        contribution = self.session.scalar(
            select(GoalContribution).where(GoalContribution.goal_id == goal.id)
        )
        self.assertIn("R$ 50,00", response)
        self.assertEqual(contribution.source, "whatsapp_text")

    def test_ambiguous_query_persists_and_resolves_clarification(self) -> None:
        question = self._message("onde gastei mais esse mês?", "ambiguous")
        pending = self.session.scalar(
            select(IntentClarification).where(
                IntentClarification.user_id == self.user.id
            )
        )

        answer = self._message("categoria", "ambiguous-answer")
        record = self.session.scalar(
            select(UnrecognizedMessage).where(
                UnrecognizedMessage.user_id == self.user.id,
                UnrecognizedMessage.message == "onde gastei mais esse mês?",
            )
        )
        correction = self.session.scalar(
            select(UnrecognizedMessage).where(
                UnrecognizedMessage.user_id == self.user.id,
                UnrecognizedMessage.message == "categoria",
            )
        )

        self.assertIn("individual", question)
        self.assertIsNotNone(pending)
        self.assertIn("Alimentação", answer)
        self.assertEqual(record.resolved_intent, "consultar_categoria_maior_gasto")
        self.assertEqual(
            correction.resolved_intent,
            "consultar_categoria_maior_gasto",
        )
        self.assertIsNone(
            self.session.scalar(
                select(IntentClarification).where(
                    IntentClarification.user_id == self.user.id
                )
            )
        )

    def test_clarification_context_is_isolated_by_user(self) -> None:
        self._message("onde gastei mais?", "isolation-a")

        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=self._unknown_intent(),
        ):
            other_response = handle_financial_message(
                self.session,
                user=self.other_user,
                text="categoria",
                whatsapp_message_id="isolation-b",
                current_date=self.current_date,
                current_datetime=self.current_time,
            )

        self.assertIn("financeira", other_response)
        self.assertIsNotNone(
            self.session.scalar(
                select(IntentClarification).where(
                    IntentClarification.user_id == self.user.id
                )
            )
        )

    def test_unrecognized_message_is_saved_without_becoming_example(self) -> None:
        response = self._message_with_unknown_financial_intent(
            "qual a capital do Brasil?",
            "unknown-natural",
        )

        record = self.session.scalar(
            select(UnrecognizedMessage).where(
                UnrecognizedMessage.user_id == self.user.id
            )
        )
        self.assertTrue("gastos" in response or "financeira" in response)
        self.assertEqual(record.message, "qual a capital do Brasil?")
        self.assertFalse(record.reviewed)
        self.assertIsNone(record.resolved_intent)
        self.assertEqual(self.session.scalar(select(func.count(IntentExample.id))), 0)

    def test_structured_ai_route_executes_only_backend_read_service(self) -> None:
        decision = NaturalIntentDecision(
            intent="consultar_maior_gasto",
            confidence=0.92,
            parameters=NaturalIntentParameters(period="current_month"),
            clarification_question=None,
            candidates=[],
        )
        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=self._unknown_intent(),
        ), patch(
            "backend.services.financial_assistant_service.route_natural_intent",
            return_value=IntentRouteOutcome(decision=decision),
        ):
            response = self._message(
                "qual foi a compra mais pesada?",
                "ai-routed-read",
            )

        self.assertIn("Mercado", response)
        self.assertEqual(
            self.session.scalar(select(func.count(FinancialTransaction.id))),
            4,
        )

    def test_existing_create_income_expense_and_export_remain_unchanged(self) -> None:
        expense = FinancialIntent(
            action="create_expense",
            amount=50,
            description="gasolina",
            category="Transporte",
            transaction_date="2026-09-23",
            needs_clarification=False,
            confidence=0.99,
        )
        income = expense.model_copy(
            update={
                "action": "create_income",
                "amount": 1000,
                "description": "salário",
                "category": "Salário",
            }
        )
        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            side_effect=[expense, income],
        ):
            expense_response = self._message(
                "gastei 50 de gasolina",
                "regression-expense",
            )
            income_response = self._message(
                "recebi 1000 de salário",
                "regression-income",
            )
        exported = self._message(
            "me manda meu extrato do mês",
            "regression-export",
        )

        self.assertIn("R$ 50,00", expense_response)
        self.assertIn("R$ 1.000,00", income_response)
        self.assertIsInstance(exported, ExportedStatement)
        self.assertEqual(
            self.session.scalar(
                select(func.count(FinancialTransaction.id)).where(
                    FinancialTransaction.whatsapp_message_id.in_(
                        ["regression-expense", "regression-income"]
                    )
                )
            ),
            2,
        )

    def _message(
        self,
        text: str,
        message_id: str,
        *,
        source: str = "whatsapp_text",
        audio_transcription: str | None = None,
    ):
        return handle_financial_message(
            self.session,
            user=self.user,
            text=text,
            whatsapp_message_id=message_id,
            current_date=self.current_date,
            source=source,
            current_datetime=self.current_time,
            audio_transcription=audio_transcription,
        )

    def _message_with_unknown_financial_intent(self, text: str, message_id: str):
        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=self._unknown_intent(),
        ):
            return self._message(text, message_id)

    @staticmethod
    def _unknown_intent() -> FinancialIntent:
        return FinancialIntent(
            action="unknown",
            needs_clarification=False,
            confidence=0.1,
        )

    def _transaction(
        self,
        transaction_type: str,
        amount: str,
        description: str,
        transaction_date: date,
        category_id: int,
    ) -> None:
        create_transaction(
            self.session,
            user_id=self.user.id,
            type=transaction_type,
            amount=amount,
            description=description,
            category_id=category_id,
            transaction_date=transaction_date,
            source="whatsapp_text",
        )

    def _user(self, email: str, phone: str) -> User:
        user = User(
            name="Usuário",
            email=email,
            whatsapp_phone=phone,
            password_hash="$argon2id$test-hash",
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user


if __name__ == "__main__":
    unittest.main()
