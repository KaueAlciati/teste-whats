import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.base import Base
from backend.database.connection import get_db
from backend.main import app
from backend.models import Category, FinancialTransaction, User
from backend.services.auth_service import create_access_token


class DashboardApiTestCase(unittest.TestCase):
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

        def override_get_db():
            with self.session_factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.environment = patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": (
                    "test-secret-with-at-least-thirty-two-characters"
                )
            },
        )
        self.environment.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.environment.stop()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_dashboard_returns_only_authenticated_user_data(self) -> None:
        with self.session_factory() as db:
            user = self._user(db, "user@example.com", "5515999999999")
            other_user = self._user(
                db,
                "other@example.com",
                "5515888888888",
            )
            category = Category(
                name="Salário",
                type="income",
                user_id=user.id,
            )
            db.add(category)
            db.commit()
            db.refresh(category)

            self._transaction(
                db,
                user_id=user.id,
                transaction_type="income",
                amount="1500.00",
                description="Salário",
                category_id=category.id,
            )
            self._transaction(
                db,
                user_id=user.id,
                transaction_type="expense",
                amount="40.00",
                description="Gasolina",
            )
            self._transaction(
                db,
                user_id=other_user.id,
                transaction_type="income",
                amount="9999.00",
                description="Dado de outro usuário",
            )
            token = create_access_token(user)
            other_user_id = other_user.id

        response = self.client.get(
            "/api/dashboard",
            params={"user_id": other_user_id},
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["balance"], 1460.0)
        self.assertEqual(body["total_income"], 1500.0)
        self.assertEqual(body["total_expense"], 40.0)
        self.assertEqual(len(body["monthly_flow"]), 6)
        self.assertEqual(body["monthly_flow"][-1]["income"], 1500.0)
        self.assertEqual(body["monthly_flow"][-1]["expense"], 40.0)
        self.assertEqual(len(body["recent_transactions"]), 2)
        descriptions = {
            item["description"] for item in body["recent_transactions"]
        }
        self.assertNotIn("Dado de outro usuário", descriptions)

    def test_dashboard_without_token_is_rejected(self) -> None:
        response = self.client.get("/api/dashboard")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    @staticmethod
    def _user(db: Session, email: str, whatsapp_phone: str) -> User:
        user = User(
            name="Usuário",
            email=email,
            whatsapp_phone=whatsapp_phone,
            password_hash="$argon2id$test-hash",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def _transaction(
        db: Session,
        *,
        user_id: int,
        transaction_type: str,
        amount: str,
        description: str,
        category_id: int | None = None,
    ) -> None:
        db.add(
            FinancialTransaction(
                user_id=user_id,
                type=transaction_type,
                amount=Decimal(amount),
                description=description,
                category_id=category_id,
                transaction_date=date.today(),
                source="whatsapp_text",
            )
        )
        db.commit()


if __name__ == "__main__":
    unittest.main()
