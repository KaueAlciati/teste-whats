import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.database.base import Base
from backend.models import Category, FinancialTransaction, User  # noqa: F401
from backend.services.financial_service import (
    DuplicateWhatsAppMessageError,
    calculate_balance,
    create_transaction,
    get_transaction,
    list_transactions,
)
from backend.services.user_service import get_or_create_whatsapp_user


class FinancialServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.user = get_or_create_whatsapp_user(
            self.session,
            "5515999999999",
        )

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_create_income(self) -> None:
        transaction = self._create_transaction(
            type="income",
            amount=Decimal("1500.00"),
            message_id="income-message",
        )

        stored_transaction = get_transaction(
            self.session,
            transaction.id,
            user_id=self.user.id,
        )
        self.assertIsNotNone(stored_transaction)
        self.assertEqual(stored_transaction.amount, Decimal("1500.00"))
        self.assertEqual(stored_transaction.type, "income")

    def test_create_expense(self) -> None:
        transaction = self._create_transaction(
            type="expense",
            amount=Decimal("125.40"),
            message_id="expense-message",
        )

        transactions = list_transactions(self.session, user_id=self.user.id)
        self.assertEqual([item.id for item in transactions], [transaction.id])
        self.assertEqual(transaction.amount, Decimal("125.40"))
        self.assertEqual(transaction.type, "expense")

    def test_calculate_balance_uses_income_minus_expense(self) -> None:
        self._create_transaction(
            type="income",
            amount=Decimal("1000.00"),
            message_id="balance-income",
        )
        self._create_transaction(
            type="expense",
            amount=Decimal("250.25"),
            message_id="balance-expense",
        )

        balance = calculate_balance(self.session, user_id=self.user.id)
        self.assertEqual(balance, Decimal("749.75"))

    def test_duplicate_whatsapp_message_id_is_rejected(self) -> None:
        self._create_transaction(
            type="expense",
            amount=Decimal("10.00"),
            message_id="same-message",
        )

        with self.assertRaises(DuplicateWhatsAppMessageError):
            self._create_transaction(
                type="expense",
                amount=Decimal("20.00"),
                message_id="same-message",
            )

        transaction_count = self.session.scalar(
            select(func.count(FinancialTransaction.id))
        )
        self.assertEqual(transaction_count, 1)

    def _create_transaction(
        self,
        *,
        type: str,
        amount: Decimal,
        message_id: str,
    ) -> FinancialTransaction:
        return create_transaction(
            self.session,
            user_id=self.user.id,
            type=type,
            amount=amount,
            description="Movimentação de teste",
            transaction_date=date(2026, 9, 18),
            source="whatsapp_text",
            whatsapp_message_id=message_id,
        )


if __name__ == "__main__":
    unittest.main()
