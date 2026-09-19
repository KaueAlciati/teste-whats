import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.base import Base
from backend.database.connection import get_db
from backend.main import app
from backend.models import FinancialTransaction, User
from backend.services.auth_service import create_access_token


class TransactionsApiTestCase(unittest.TestCase):
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

        with self.session_factory() as db:
            self.user = self._user(
                db,
                email="user@example.com",
                phone="5515999999999",
            )
            self.other_user = self._user(
                db,
                email="other@example.com",
                phone="5515888888888",
            )
            self.token = create_access_token(self.user)
            self.other_token = create_access_token(self.other_user)

        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.environment.stop()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_create_and_list_use_only_authenticated_user(self) -> None:
        created = self._create(self.token)
        self._create(
            self.other_token,
            description="Transação de outro usuário",
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["source"], "dashboard_manual")
        self.assertEqual(created.json()["category"], "Alimentação")

        response = self.client.get(
            "/api/transactions",
            params={"user_id": self.other_user.id},
            headers=self._headers(self.token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["description"], "Mercado")
        self.assertNotIn(
            "Transação de outro usuário",
            {item["description"] for item in response.json()},
        )

        with self.session_factory() as db:
            transaction = db.scalar(
                select(FinancialTransaction).where(
                    FinancialTransaction.id == created.json()["id"]
                )
            )
            self.assertIsNotNone(transaction)
            self.assertEqual(transaction.user_id, self.user.id)
            self.assertEqual(transaction.source, "dashboard_manual")

    def test_create_rejects_frontend_user_id(self) -> None:
        payload = self._payload()
        payload["user_id"] = self.other_user.id

        response = self.client.post(
            "/api/transactions",
            json=payload,
            headers=self._headers(self.token),
        )

        self.assertEqual(response.status_code, 422)

    def test_update_and_delete_owned_transaction(self) -> None:
        created = self._create(self.token).json()
        updated_payload = self._payload(
            description="Salário",
            amount=2500.0,
            transaction_type="income",
            category="Salário",
        )

        updated = self.client.put(
            f"/api/transactions/{created['id']}",
            json=updated_payload,
            headers=self._headers(self.token),
        )

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["description"], "Salário")
        self.assertEqual(updated.json()["amount"], 2500.0)
        self.assertEqual(updated.json()["type"], "income")
        self.assertEqual(updated.json()["source"], "dashboard_manual")

        deleted = self.client.delete(
            f"/api/transactions/{created['id']}",
            headers=self._headers(self.token),
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"status": "ok"})

        listed = self.client.get(
            "/api/transactions",
            headers=self._headers(self.token),
        )
        self.assertEqual(listed.json(), [])

    def test_user_cannot_update_or_delete_another_users_transaction(self) -> None:
        other_transaction = self._create(self.other_token).json()

        update = self.client.put(
            f"/api/transactions/{other_transaction['id']}",
            json=self._payload(description="Tentativa indevida"),
            headers=self._headers(self.token),
        )
        delete = self.client.delete(
            f"/api/transactions/{other_transaction['id']}",
            headers=self._headers(self.token),
        )

        self.assertEqual(update.status_code, 404)
        self.assertEqual(delete.status_code, 404)
        with self.session_factory() as db:
            self.assertIsNotNone(
                db.get(FinancialTransaction, other_transaction["id"])
            )

    def test_transactions_require_authentication(self) -> None:
        response = self.client.get("/api/transactions")

        self.assertEqual(response.status_code, 401)

    def test_cors_allows_transaction_updates(self) -> None:
        response = self.client.options(
            "/api/transactions/1",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("PUT", response.headers["access-control-allow-methods"])

    def _create(
        self,
        token: str,
        *,
        description: str = "Mercado",
    ):
        return self.client.post(
            "/api/transactions",
            json=self._payload(description=description),
            headers=self._headers(token),
        )

    @staticmethod
    def _payload(
        *,
        description: str = "Mercado",
        amount: float = 40.0,
        transaction_type: str = "expense",
        category: str = "Alimentação",
    ) -> dict:
        return {
            "description": description,
            "amount": amount,
            "type": transaction_type,
            "category": category,
            "date": "2026-09-19",
        }

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _user(db, *, email: str, phone: str) -> User:
        user = User(
            name="Usuário",
            email=email,
            whatsapp_phone=phone,
            password_hash="$argon2id$test-hash",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


if __name__ == "__main__":
    unittest.main()
