import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.base import Base
from backend.models import Notification, User
from backend.services.financial_service import TRANSACTION_SOURCES, create_transaction


class SpendingAlertsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    def tearDown(self) -> None:
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_thresholds_and_monthly_deduplication(self) -> None:
        with self.session_factory() as db:
            user = self._user(db, "5515999999901", enabled=True)
            self._transaction(db, user.id, "income", "1000", "Renda")
            self._transaction(db, user.id, "expense", "300", "Despesa 1")
            self._transaction(db, user.id, "expense", "250", "Despesa 2")
            self._transaction(db, user.id, "expense", "250", "Despesa 3")
            self._transaction(db, user.id, "expense", "200", "Despesa 4")
            self._transaction(db, user.id, "expense", "10", "Despesa 5")

            notifications = list(
                db.scalars(
                    select(Notification)
                    .where(Notification.user_id == user.id)
                    .order_by(Notification.rule_code)
                )
            )

        self.assertEqual(
            [item.rule_code for item in notifications],
            [
                "monthly_expenses_100",
                "monthly_expenses_80",
                "single_expense_30",
            ],
        )
        self.assertEqual(
            len({(item.rule_code, item.period_key) for item in notifications}),
            3,
        )
        critical = next(
            item
            for item in notifications
            if item.rule_code == "monthly_expenses_100"
        )
        self.assertEqual(critical.priority, "urgent")

    def test_disabled_preference_and_zero_income_create_no_alerts(self) -> None:
        with self.session_factory() as db:
            disabled = self._user(db, "5515999999902", enabled=False)
            no_income = self._user(db, "5515999999903", enabled=True)
            self._transaction(db, disabled.id, "income", "1000", "Renda")
            self._transaction(db, disabled.id, "expense", "900", "Despesa")
            self._transaction(db, no_income.id, "expense", "900", "Despesa")

            notifications = list(db.scalars(select(Notification)))

        self.assertEqual(notifications, [])

    def test_every_transaction_source_uses_the_same_alert_evaluator(self) -> None:
        with self.session_factory() as db:
            user = self._user(db, "5515999999904", enabled=True)
            for month, source in enumerate(sorted(TRANSACTION_SOURCES), start=1):
                transaction_date = date(2026, month, 10)
                batched = source.startswith("import_")
                self._transaction(
                    db,
                    user.id,
                    "income",
                    "1000",
                    f"Renda {source}",
                    transaction_date=transaction_date,
                    source=source,
                    commit=not batched,
                )
                self._transaction(
                    db,
                    user.id,
                    "expense",
                    "300",
                    f"Despesa {source}",
                    transaction_date=transaction_date,
                    source=source,
                    commit=not batched,
                )
                if batched:
                    db.commit()

            notifications = list(
                db.scalars(
                    select(Notification).where(
                        Notification.user_id == user.id,
                        Notification.rule_code == "single_expense_30",
                    )
                )
            )

        self.assertEqual(len(notifications), len(TRANSACTION_SOURCES))

    @staticmethod
    def _user(db, phone: str, *, enabled: bool) -> User:
        user = User(
            name="Usuário",
            email=f"{phone}@example.com",
            whatsapp_phone=phone,
            password_hash="$argon2id$test",
            critical_spending_alerts_enabled=enabled,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def _transaction(
        db,
        user_id: int,
        transaction_type: str,
        amount: str,
        description: str,
        *,
        transaction_date: date = date(2026, 1, 10),
        source: str = "dashboard_manual",
        commit: bool = True,
    ) -> None:
        create_transaction(
            db,
            user_id=user_id,
            type=transaction_type,
            amount=Decimal(amount),
            description=description,
            transaction_date=transaction_date,
            source=source,
            commit=commit,
        )


if __name__ == "__main__":
    unittest.main()
