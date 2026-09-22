import os
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.base import Base
from backend.database.connection import get_db
from backend.main import app
from backend.models import (
    FinancialProfile,
    FinancialTransaction,
    Goal,
    GoalContext,
    GoalContribution,
    PendingAudioConfirmation,
    PendingReceipt,
    User,
)


class SettingsApiTestCase(unittest.TestCase):
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
                "JWT_SECRET_KEY": "test-secret-with-at-least-thirty-two-characters",
                "JWT_EXPIRE_MINUTES": "60",
            },
        )
        self.environment.start()
        self.client = TestClient(app)
        self.user_a = self._register_and_login(
            name="Usuário A",
            email="a@example.com",
            phone="5515999999991",
        )
        self.user_b = self._register_and_login(
            name="Usuário B",
            email="b@example.com",
            phone="5515999999992",
        )

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.environment.stop()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_load_settings_uses_authenticated_profile(self) -> None:
        response = self.client.get("/api/auth/me", headers=self.user_a["headers"])

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["name"], "Usuário A")
        self.assertEqual(body["email"], "a@example.com")
        self.assertEqual(body["whatsapp_phone"], "5515999999991")
        self.assertFalse(body["whatsapp_verified"])
        self.assertIn("created_at", body)
        self.assertNotIn("password_hash", body)

    def test_edit_name_and_email(self) -> None:
        response = self.client.put(
            "/api/auth/profile",
            headers=self.user_a["headers"],
            json={"name": "  Novo   Nome ", "email": "NOVO@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Novo Nome")
        self.assertEqual(response.json()["email"], "novo@example.com")

    def test_duplicate_email_is_rejected(self) -> None:
        response = self.client.put(
            "/api/auth/profile",
            headers=self.user_a["headers"],
            json={"email": "B@EXAMPLE.COM"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "E-mail já cadastrado")

    def test_change_password_with_correct_current_password(self) -> None:
        response = self.client.post(
            "/api/auth/change-password",
            headers=self.user_a["headers"],
            json={
                "current_password": "senha-segura-123",
                "new_password": "nova-senha-456",
                "confirm_new_password": "nova-senha-456",
            },
        )

        self.assertEqual(response.status_code, 200)
        old_login = self._login("a@example.com", "senha-segura-123")
        new_login = self._login("a@example.com", "nova-senha-456")
        self.assertEqual(old_login.status_code, 401)
        self.assertEqual(new_login.status_code, 200)

    def test_change_password_rejects_wrong_current_password(self) -> None:
        response = self.client.post(
            "/api/auth/change-password",
            headers=self.user_a["headers"],
            json={
                "current_password": "senha-incorreta",
                "new_password": "nova-senha-456",
                "confirm_new_password": "nova-senha-456",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Senha atual incorreta")

    def test_profile_update_is_isolated_and_does_not_accept_user_id(self) -> None:
        rejected = self.client.put(
            "/api/auth/profile",
            headers=self.user_a["headers"],
            json={"name": "Invasão", "user_id": self.user_b["id"]},
        )
        self.assertEqual(rejected.status_code, 422)

        updated = self.client.put(
            "/api/auth/profile",
            headers=self.user_a["headers"],
            json={"name": "Somente A"},
        )
        self.assertEqual(updated.status_code, 200)

        b_profile = self.client.get(
            "/api/auth/me",
            headers=self.user_b["headers"],
        )
        self.assertEqual(b_profile.json()["name"], "Usuário B")

    def test_clear_financial_history_is_isolated_and_preserves_account(self) -> None:
        self._create_financial_history(self.user_a["id"], suffix="a")
        self._create_financial_history(self.user_b["id"], suffix="b")

        response = self.client.request(
            "DELETE",
            "/api/auth/financial-history",
            headers=self.user_a["headers"],
            json={"confirmation": "LIMPAR HISTÓRICO"},
        )
        self.assertEqual(response.status_code, 200)

        with self.session_factory() as db:
            self.assertIsNotNone(db.get(User, self.user_a["id"]))
            self.assertEqual(self._count_owned(db, FinancialTransaction, self.user_a["id"]), 0)
            self.assertEqual(self._count_owned(db, Goal, self.user_a["id"]), 0)
            self.assertEqual(self._count_owned(db, GoalContribution, self.user_a["id"]), 0)
            self.assertEqual(self._count_owned(db, GoalContext, self.user_a["id"]), 0)
            self.assertEqual(self._count_owned(db, PendingReceipt, self.user_a["id"]), 0)
            self.assertEqual(self._count_owned(db, PendingAudioConfirmation, self.user_a["id"]), 0)
            profile = db.scalar(
                select(FinancialProfile).where(FinancialProfile.user_id == self.user_a["id"])
            )
            self.assertIsNotNone(profile)
            self.assertIsNone(profile.analysis_cache)
            self.assertGreater(self._count_owned(db, FinancialTransaction, self.user_b["id"]), 0)
            self.assertGreater(self._count_owned(db, Goal, self.user_b["id"]), 0)

        me = self.client.get("/api/auth/me", headers=self.user_a["headers"])
        self.assertEqual(me.status_code, 200)

    def test_delete_account_removes_only_authenticated_account(self) -> None:
        self._create_financial_history(self.user_a["id"], suffix="delete")
        self._create_financial_history(self.user_b["id"], suffix="keep")

        response = self.client.request(
            "DELETE",
            "/api/auth/account",
            headers=self.user_a["headers"],
            json={"confirmation": "EXCLUIR CONTA"},
        )
        self.assertEqual(response.status_code, 200)

        with self.session_factory() as db:
            self.assertIsNone(db.get(User, self.user_a["id"]))
            self.assertIsNotNone(db.get(User, self.user_b["id"]))
            self.assertEqual(self._count_owned(db, FinancialTransaction, self.user_a["id"]), 0)
            self.assertGreater(self._count_owned(db, FinancialTransaction, self.user_b["id"]), 0)

        deleted_me = self.client.get("/api/auth/me", headers=self.user_a["headers"])
        remaining_me = self.client.get("/api/auth/me", headers=self.user_b["headers"])
        self.assertEqual(deleted_me.status_code, 401)
        self.assertEqual(remaining_me.status_code, 200)

    def _register_and_login(self, *, name: str, email: str, phone: str) -> dict:
        registered = self.client.post(
            "/api/auth/register",
            json={
                "name": name,
                "email": email,
                "whatsapp_phone": phone,
                "password": "senha-segura-123",
            },
        )
        self.assertEqual(registered.status_code, 201)
        login = self._login(email, "senha-segura-123")
        self.assertEqual(login.status_code, 200)
        token = login.json()["access_token"]
        return {
            "id": registered.json()["id"],
            "headers": {"Authorization": f"Bearer {token}"},
        }

    def _login(self, email: str, password: str):
        return self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )

    def _create_financial_history(self, user_id: int, *, suffix: str) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as db:
            transaction = FinancialTransaction(
                user_id=user_id,
                type="expense",
                amount=Decimal("10.00"),
                description=f"Compra {suffix}",
                transaction_date=date.today(),
                source="dashboard_manual",
            )
            goal = Goal(
                user_id=user_id,
                name=f"Meta {suffix}",
                target_amount=Decimal("100.00"),
                current_amount=Decimal("10.00"),
                status="active",
            )
            db.add_all([transaction, goal])
            db.flush()
            db.add_all(
                [
                    GoalContribution(
                        user_id=user_id,
                        goal_id=goal.id,
                        amount=Decimal("10.00"),
                        source="dashboard",
                    ),
                    GoalContext(
                        user_id=user_id,
                        goal_id=goal.id,
                        expires_at=now + timedelta(minutes=30),
                    ),
                    PendingReceipt(
                        user_id=user_id,
                        whatsapp_message_id=f"receipt-{suffix}-{user_id}",
                        extracted_data={"amount": 10},
                        expires_at=now + timedelta(minutes=30),
                    ),
                    PendingAudioConfirmation(
                        user_id=user_id,
                        original_whatsapp_message_id=f"audio-{suffix}-{user_id}",
                        transcription="gastei dez",
                        expires_at=now + timedelta(minutes=30),
                    ),
                    FinancialProfile(
                        user_id=user_id,
                        main_goal="organize_finances",
                        investment_horizon="up_to_1_year",
                        risk_profile="conservative",
                        liquidity_need="high",
                        has_debts=False,
                        income_type="fixed",
                        main_priority="organize_budget",
                        onboarding_completed=True,
                        analysis_cache={"stale": True},
                        analysis_generated_at=now,
                    ),
                ]
            )
            db.commit()

    @staticmethod
    def _count_owned(db, model, user_id: int) -> int:
        return len(db.scalars(select(model).where(model.user_id == user_id)).all())


if __name__ == "__main__":
    unittest.main()
