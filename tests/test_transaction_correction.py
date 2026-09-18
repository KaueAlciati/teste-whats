import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.database.base import Base
from backend.models import Category, FinancialTransaction, User  # noqa: F401
from backend.schemas.financial_intent import FinancialIntent
from backend.services.financial_assistant_service import handle_financial_message
from backend.services.financial_service import (
    create_transaction,
    update_transaction,
)
from backend.services.user_service import get_or_create_whatsapp_user


class TransactionCorrectionTestCase(unittest.TestCase):
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
        self.current_datetime = datetime.now(timezone(timedelta(hours=-3)))

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_audio_expense_then_amount_correction_keeps_one_transaction(self) -> None:
        creation = self._intent(
            action="create_expense",
            amount=30,
            description="gasolina",
            category="Transporte",
            transaction_date="2026-09-18",
            confidence=0.98,
        )
        correction = self._intent(
            action="correct_last_transaction",
            amount=50,
            confidence=0.98,
        )

        audio_response = self._handle(
            "gastei 30 reais de gasolina hoje",
            creation,
            "audio-original",
            source="whatsapp_audio",
            audio_transcription="gastei 30 reais de gasolina hoje",
        )
        correction_response = self._handle(
            "não, era 50 reais",
            correction,
            "text-correction-amount",
        )

        transactions = list(self.session.scalars(select(FinancialTransaction)))
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].amount, Decimal("50.00"))
        self.assertEqual(transactions[0].source, "whatsapp_audio")
        self.assertIn("🎧 Entendi", audio_response)
        self.assertIn("R$ 50,00", correction_response)

    def test_description_correction_updates_latest_transaction(self) -> None:
        transaction = self._create_recent_transaction(
            description="gasolina",
            amount="30.00",
        )
        correction = self._intent(
            action="correct_last_transaction",
            description="Diesel",
        )

        response = self._handle(
            "era diesel, não gasolina",
            correction,
            "description-correction",
        )

        self.session.refresh(transaction)
        self.assertEqual(transaction.description, "Diesel")
        self.assertIn("Diesel", response)

    def test_type_correction_requires_high_confidence(self) -> None:
        transaction = self._create_recent_transaction()
        correction = self._intent(
            action="correct_last_transaction",
            transaction_type="income",
            confidence=0.80,
        )

        response = self._handle(
            "na verdade foi uma receita",
            correction,
            "type-correction-low-confidence",
        )

        self.session.refresh(transaction)
        self.assertEqual(transaction.type, "expense")
        self.assertIn("quer mesmo trocar o tipo", response.lower())

    def test_category_correction_uses_existing_category(self) -> None:
        transaction = self._create_recent_transaction()
        correction = self._intent(
            action="correct_last_transaction",
            category="Compras",
        )

        response = self._handle(
            "coloca em Compras",
            correction,
            "category-correction",
        )

        self.session.refresh(transaction)
        self.assertEqual(transaction.category.name, "Compras")
        self.assertIn("Compras", response)

    def test_date_correction_updates_to_yesterday(self) -> None:
        transaction = self._create_recent_transaction()
        yesterday = self.current_date - timedelta(days=1)
        correction = self._intent(
            action="correct_last_transaction",
            transaction_date=yesterday.isoformat(),
        )

        response = self._handle(
            "foi ontem",
            correction,
            "date-correction",
        )

        self.session.refresh(transaction)
        self.assertEqual(transaction.transaction_date, yesterday)
        self.assertIn("Ontem", response)

    def test_complete_new_expense_creates_new_transaction(self) -> None:
        original = self._create_recent_transaction(
            description="gasolina",
            amount="30.00",
        )
        new_expense = self._intent(
            action="create_expense",
            amount=20,
            description="café",
            category="Alimentação",
            transaction_date="2026-09-18",
        )

        self._handle(
            "gastei 20 no café",
            new_expense,
            "new-expense",
        )

        transaction_count = self.session.scalar(
            select(func.count(FinancialTransaction.id))
        )
        self.session.refresh(original)
        self.assertEqual(transaction_count, 2)
        self.assertEqual(original.amount, Decimal("30.00"))

    def test_other_user_cannot_update_transaction(self) -> None:
        transaction = self._create_recent_transaction()
        other_user = get_or_create_whatsapp_user(
            self.session,
            "5515888888888",
        )

        with self.assertRaises(PermissionError):
            update_transaction(
                self.session,
                transaction=transaction,
                user_id=other_user.id,
                amount=Decimal("999.00"),
            )

        self.session.refresh(transaction)
        self.assertEqual(transaction.amount, Decimal("30.00"))

    def test_expired_transaction_is_not_corrected(self) -> None:
        transaction = self._create_recent_transaction()
        transaction.created_at = self.current_datetime - timedelta(minutes=16)
        self.session.commit()
        correction = self._intent(
            action="correct_last_transaction",
            amount=50,
        )

        response = self._handle(
            "não, era 50",
            correction,
            "expired-correction",
        )

        self.session.refresh(transaction)
        self.assertEqual(transaction.amount, Decimal("30.00"))
        self.assertIn("Não achei um lançamento recente", response)

    def test_invalid_category_does_not_change_transaction(self) -> None:
        transaction = self._create_recent_transaction()
        original_category_id = transaction.category_id
        correction = self._intent(
            action="correct_last_transaction",
            category="Categoria inventada",
        )

        response = self._handle(
            "coloca em categoria inventada",
            correction,
            "invalid-category-correction",
        )

        self.session.refresh(transaction)
        self.assertEqual(transaction.category_id, original_category_id)
        self.assertIn("Não encontrei essa categoria", response)

    def test_invalid_amount_is_rejected_by_update_service(self) -> None:
        transaction = self._create_recent_transaction()

        with self.assertRaises(ValueError):
            update_transaction(
                self.session,
                transaction=transaction,
                user_id=self.user.id,
                amount=Decimal("-1.00"),
            )

        self.session.refresh(transaction)
        self.assertEqual(transaction.amount, Decimal("30.00"))

    def test_low_confidence_audio_requests_confirmation_without_registering(self) -> None:
        intent = self._intent(
            action="create_expense",
            amount=30,
            description="gasolina",
            category="Transporte",
            confidence=0.50,
        )

        response = self._handle(
            "gastei 30 reais de gasolina",
            intent,
            "low-confidence-audio",
            source="whatsapp_audio",
            audio_transcription="gastei 30 reais de gasolina",
        )

        self.assertEqual(self._transaction_count(), 0)
        self.assertIn("Foi isso mesmo?", response)

    def test_cancel_only_requests_confirmation_and_keeps_transaction(self) -> None:
        self._create_recent_transaction()
        intent = self._intent(action="cancel_last_transaction")

        response = self._handle(
            "apaga o último",
            intent,
            "cancel-request",
        )

        self.assertEqual(self._transaction_count(), 1)
        self.assertIn("Quer que eu apague", response)

    def _handle(
        self,
        text: str,
        intent: FinancialIntent,
        message_id: str,
        *,
        source: str = "whatsapp_text",
        audio_transcription: str | None = None,
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
                current_datetime=self.current_datetime,
                audio_transcription=audio_transcription,
            )

    def _create_recent_transaction(
        self,
        *,
        description: str = "gasolina",
        amount: str = "30.00",
    ) -> FinancialTransaction:
        category = self.session.scalar(
            select(Category).where(
                Category.name == "Transporte",
                Category.type == "expense",
            )
        )
        return create_transaction(
            self.session,
            user_id=self.user.id,
            type="expense",
            amount=Decimal(amount),
            description=description,
            category_id=category.id,
            transaction_date=self.current_date,
            source="whatsapp_text",
            whatsapp_message_id=f"seed-{self._transaction_count()}",
        )

    def _transaction_count(self) -> int:
        return self.session.scalar(select(func.count(FinancialTransaction.id))) or 0

    def _seed_categories(self) -> None:
        categories = {
            "expense": ("Alimentação", "Transporte", "Compras", "Outros"),
            "income": ("Salário", "Venda", "Outros"),
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
        transaction_type: str | None = None,
        period: str | None = None,
        needs_clarification: bool = False,
        clarification_question: str | None = None,
        confidence: float = 0.95,
    ) -> FinancialIntent:
        return FinancialIntent(
            action=action,
            amount=amount,
            description=description,
            category=category,
            transaction_date=transaction_date,
            payment_method=payment_method,
            type=transaction_type,
            period=period,
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
            confidence=confidence,
        )


if __name__ == "__main__":
    unittest.main()
