import asyncio
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from backend.database.base import Base
from backend.models import Category, FinancialTransaction, User  # noqa: F401
from backend.schemas.financial_intent import FinancialIntent
from backend.services.ai_financial_service import FinancialAIServiceError
from backend.services.financial_assistant_service import (
    AI_ERROR_MESSAGE,
    DATABASE_ERROR_MESSAGE,
    UNKNOWN_MESSAGE,
    handle_financial_message,
    process_financial_message,
)
from backend.services.financial_service import create_transaction
from backend.services.user_service import get_or_create_whatsapp_user


class FinancialAssistantServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self._seed_categories()
        self.user = get_or_create_whatsapp_user(
            self.session,
            "5515999999999",
        )
        self.current_date = date(2026, 9, 18)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_expense_message_creates_expense(self) -> None:
        intent = self._intent(
            action="create_expense",
            amount=40,
            description="gasolina",
            category="Transporte",
            transaction_date="2026-09-18",
        )

        response = self._handle(
            "gastei 40 reais de gasolina",
            intent,
            "expense-message",
        )

        transaction = self.session.scalar(
            select(FinancialTransaction).where(
                FinancialTransaction.whatsapp_message_id == "expense-message"
            )
        )
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.type, "expense")
        self.assertEqual(transaction.amount, Decimal("40.00"))
        self.assertEqual(transaction.source, "whatsapp_text")
        self.assertIn("Despesa registrada", response)
        self.assertIn("R$ 40,00", response)
        self.assertIn("Gasolina", response)
        self.assertIn("Transporte", response)

    def test_income_message_creates_income(self) -> None:
        intent = self._intent(
            action="create_income",
            amount=1500,
            description="salário",
            category="Salário",
            transaction_date="2026-09-18",
        )

        response = self._handle(
            "recebi 1500 de salário",
            intent,
            "income-message",
        )

        transaction = self.session.scalar(
            select(FinancialTransaction).where(
                FinancialTransaction.whatsapp_message_id == "income-message"
            )
        )
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.type, "income")
        self.assertEqual(transaction.amount, Decimal("1500.00"))
        self.assertIn("Receita registrada", response)
        self.assertIn("R$ 1.500,00", response)
        self.assertIn("Salário", response)

    def test_audio_expense_uses_existing_flow_and_audio_source(self) -> None:
        intent = self._intent(
            action="create_expense",
            amount=80,
            description="diesel",
            category="Transporte",
            transaction_date="2026-09-18",
        )

        response = self._handle(
            "gastei 80 reais de diesel hoje",
            intent,
            "audio-expense",
            source="whatsapp_audio",
        )

        transaction = self.session.scalar(
            select(FinancialTransaction).where(
                FinancialTransaction.whatsapp_message_id == "audio-expense"
            )
        )
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.source, "whatsapp_audio")
        self.assertEqual(transaction.amount, Decimal("80.00"))
        self.assertIn("Diesel", response)

    def test_audio_income_uses_existing_flow_and_audio_source(self) -> None:
        intent = self._intent(
            action="create_income",
            amount=2500,
            description="salário",
            category="Salário",
            transaction_date="2026-09-18",
        )

        response = self._handle(
            "recebi dois mil e quinhentos de salário",
            intent,
            "audio-income",
            source="whatsapp_audio",
        )

        transaction = self.session.scalar(
            select(FinancialTransaction).where(
                FinancialTransaction.whatsapp_message_id == "audio-income"
            )
        )
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.source, "whatsapp_audio")
        self.assertEqual(transaction.amount, Decimal("2500.00"))
        self.assertIn("R$ 2.500,00", response)

    def test_balance_query_is_calculated_by_backend(self) -> None:
        self._create_transaction("income", "1000.00", "balance-income")
        self._create_transaction("expense", "250.25", "balance-expense")
        intent = self._intent(action="query_balance", period="all")

        response = self._handle("quanto eu tenho?", intent, "balance-query")

        self.assertEqual(
            response,
            "💰 *Seu saldo atual*\n\n*R$ 749,75*",
        )

    def test_expense_query_uses_current_month_period(self) -> None:
        self._create_transaction(
            "expense",
            "40.00",
            "current-expense",
            transaction_date=date(2026, 9, 10),
        )
        self._create_transaction(
            "expense",
            "90.00",
            "previous-expense",
            transaction_date=date(2026, 8, 10),
        )
        intent = self._intent(
            action="query_expenses",
            period="current_month",
        )

        response = self._handle(
            "quanto gastei esse mês?",
            intent,
            "expense-query",
        )

        self.assertEqual(
            response,
            "💸 *Gastos — Este mês*\n\n*R$ 40,00*",
        )

    def test_income_query_uses_current_month_period(self) -> None:
        self._create_transaction(
            "income",
            "3200.00",
            "current-income",
            transaction_date=date(2026, 9, 5),
        )
        self._create_transaction(
            "income",
            "800.00",
            "previous-income",
            transaction_date=date(2026, 8, 5),
        )
        intent = self._intent(
            action="query_income",
            period="current_month",
        )

        response = self._handle(
            "quanto recebi esse mês?",
            intent,
            "income-query",
        )

        self.assertEqual(response, "🟢 *Entradas — Este mês*\n\n*R$ 3.200,00*")

    def test_duplicate_message_creates_only_one_transaction(self) -> None:
        intent = self._intent(
            action="create_expense",
            amount=25,
            description="café",
            category="Alimentação",
        )

        first_response = self._handle("gastei 25 em café", intent, "duplicate-id")
        second_response = self._handle("gastei 25 em café", intent, "duplicate-id")

        transaction_count = self.session.scalar(
            select(func.count(FinancialTransaction.id)).where(
                FinancialTransaction.whatsapp_message_id == "duplicate-id"
            )
        )
        self.assertIsNotNone(first_response)
        self.assertIsNone(second_response)
        self.assertEqual(transaction_count, 1)

    def test_duplicate_audio_creates_only_one_transaction(self) -> None:
        intent = self._intent(
            action="create_expense",
            amount=50,
            description="almoço",
            category="Alimentação",
        )

        first_response = self._handle(
            "paguei cinquenta reais no almoço",
            intent,
            "duplicate-audio-id",
            source="whatsapp_audio",
        )
        second_response = self._handle(
            "paguei cinquenta reais no almoço",
            intent,
            "duplicate-audio-id",
            source="whatsapp_audio",
        )

        transaction_count = self.session.scalar(
            select(func.count(FinancialTransaction.id)).where(
                FinancialTransaction.whatsapp_message_id
                == "duplicate-audio-id"
            )
        )
        self.assertIsNotNone(first_response)
        self.assertIsNone(second_response)
        self.assertEqual(transaction_count, 1)

    def test_missing_amount_does_not_create_transaction(self) -> None:
        intent = self._intent(
            action="create_expense",
            amount=None,
            description="mercado",
            category="Alimentação",
            needs_clarification=True,
            clarification_question="Quanto você gastou no mercado?",
        )

        response = self._handle("gastei no mercado", intent, "missing-amount")

        self.assertEqual(response, "Quanto você gastou no mercado?")
        self.assertEqual(self._transaction_count(), 0)

    def test_invalid_date_does_not_create_transaction(self) -> None:
        intent = self._intent(
            action="create_expense",
            amount=30,
            description="almoço",
            category="Alimentação",
            transaction_date="2026-02-30",
        )

        response = self._handle(
            "gastei 30 com almoço em uma data inválida",
            intent,
            "invalid-date",
        )

        self.assertIn("entender a data", response)
        self.assertEqual(self._transaction_count(), 0)

    def test_unknown_category_falls_back_to_others(self) -> None:
        intent = self._intent(
            action="create_expense",
            amount=15,
            description="item diverso",
            category="Categoria inexistente",
        )

        response = self._handle(
            "gastei 15 em algo diferente",
            intent,
            "fallback-category",
        )

        transaction = self.session.scalar(
            select(FinancialTransaction).where(
                FinancialTransaction.whatsapp_message_id == "fallback-category"
            )
        )
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.category.name, "Outros")
        self.assertIn("Outros", response)

    def test_unknown_action_does_not_create_transaction(self) -> None:
        intent = self._intent(action="unknown")

        response = self._handle("qual a capital do Brasil?", intent, "unknown-id")

        self.assertIn("organização financeira", response)
        self.assertNotEqual(response, UNKNOWN_MESSAGE)
        self.assertEqual(self._transaction_count(), 0)

    def test_different_users_do_not_share_balances(self) -> None:
        other_user = get_or_create_whatsapp_user(
            self.session,
            "5515888888888",
        )
        self._create_transaction("income", "500.00", "user-one-income")
        create_transaction(
            self.session,
            user_id=other_user.id,
            type="expense",
            amount=Decimal("30.00"),
            description="Teste",
            transaction_date=self.current_date,
            source="whatsapp_text",
            whatsapp_message_id="user-two-expense",
        )
        intent = self._intent(action="query_balance", period="all")

        first_response = self._handle(
            "quanto eu tenho?",
            intent,
            "user-one-query",
        )
        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=intent,
        ):
            second_response = handle_financial_message(
                self.session,
                user=other_user,
                text="quanto eu tenho?",
                whatsapp_message_id="user-two-query",
                current_date=self.current_date,
            )

        self.assertIn("R$ 500,00", first_response)
        self.assertIn("R$ -30,00", second_response)

    def test_openai_error_is_caught_and_user_gets_safe_message(self) -> None:
        send_mock = AsyncMock(return_value=True)
        with patch(
            "backend.services.financial_assistant_service._process_financial_message",
            side_effect=FinancialAIServiceError("internal error"),
        ):
            with patch(
                "backend.services.financial_assistant_service.send_text_message",
                send_mock,
            ):
                asyncio.run(
                    process_financial_message(
                        "5515999999999",
                        "ai-error-id",
                        "gastei 10",
                    )
                )

        send_mock.assert_awaited_once_with("5515999999999", AI_ERROR_MESSAGE)

    def test_database_error_does_not_send_success_message(self) -> None:
        send_mock = AsyncMock(return_value=True)
        with patch(
            "backend.services.financial_assistant_service._process_financial_message",
            side_effect=SQLAlchemyError("database unavailable"),
        ):
            with patch(
                "backend.services.financial_assistant_service.send_text_message",
                send_mock,
            ):
                asyncio.run(
                    process_financial_message(
                        "5515999999999",
                        "database-error-id",
                        "gastei 10 reais em chocolate",
                    )
                )

        send_mock.assert_awaited_once_with(
            "5515999999999",
            DATABASE_ERROR_MESSAGE,
        )
        self.assertNotIn("registrei", DATABASE_ERROR_MESSAGE)
        self.assertNotIn("salvo", DATABASE_ERROR_MESSAGE)

    def _handle(
        self,
        text: str,
        intent: FinancialIntent,
        message_id: str,
        *,
        source: str = "whatsapp_text",
    ) -> str | None:
        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message",
            return_value=intent,
        ):
            return handle_financial_message(
                self.session,
                user=self.user,
                text=text,
                whatsapp_message_id=message_id,
                current_date=self.current_date,
                source=source,
            )

    def _create_transaction(
        self,
        transaction_type: str,
        amount: str,
        message_id: str,
        *,
        transaction_date: date | None = None,
    ) -> FinancialTransaction:
        return create_transaction(
            self.session,
            user_id=self.user.id,
            type=transaction_type,
            amount=Decimal(amount),
            description="Teste",
            transaction_date=transaction_date or self.current_date,
            source="whatsapp_text",
            whatsapp_message_id=message_id,
        )

    def _transaction_count(self) -> int:
        return self.session.scalar(select(func.count(FinancialTransaction.id))) or 0

    def _seed_categories(self) -> None:
        categories = {
            "expense": (
                "Alimentação",
                "Transporte",
                "Outros",
            ),
            "income": (
                "Salário",
                "Venda",
                "Outros",
            ),
        }
        for transaction_type, names in categories.items():
            self.session.add_all(
                Category(
                    name=name,
                    type=transaction_type,
                    user_id=None,
                    is_default=True,
                )
                for name in names
            )
        self.session.commit()

    @staticmethod
    def _intent(
        *,
        action: str,
        amount: float | None = None,
        description: str | None = None,
        category: str | None = None,
        transaction_date: str | None = None,
        payment_method: str | None = None,
        period: str | None = None,
        needs_clarification: bool = False,
        clarification_question: str | None = None,
    ) -> FinancialIntent:
        return FinancialIntent(
            action=action,
            amount=amount,
            description=description,
            category=category,
            transaction_date=transaction_date,
            payment_method=payment_method,
            period=period,
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
            confidence=0.95,
        )


if __name__ == "__main__":
    unittest.main()
