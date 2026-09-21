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
from backend.models import (
    Category,
    FinancialTransaction,
    Goal,
    GoalContribution,
    User,
)
from backend.schemas.insights import AIInsightsContent
from backend.services.auth_service import create_access_token
from backend.services.insights_ai_service import InsightsAIServiceError
from backend.services.insights_calculation_service import (
    calculate_financial_summary,
)


class InsightsApiTestCase(unittest.TestCase):
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
            self.user = self._user(db, "user@example.com", "5515999999999")
            self.other_user = self._user(
                db,
                "other@example.com",
                "5515888888888",
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

    def test_new_user_has_incomplete_profile_and_jwt_is_required(self) -> None:
        response = self.client.get(
            "/api/insights/profile",
            headers=self._headers(self.token),
        )
        unauthorized = self.client.get("/api/insights/profile")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"onboarding_completed": False, "profile": None},
        )
        self.assertEqual(unauthorized.status_code, 401)

    def test_profile_create_update_and_user_isolation(self) -> None:
        created = self.client.post(
            "/api/insights/profile",
            json=self._profile_payload(),
            headers=self._headers(self.token),
        )
        duplicate = self.client.post(
            "/api/insights/profile",
            json=self._profile_payload(),
            headers=self._headers(self.token),
        )
        other_profile = self.client.get(
            "/api/insights/profile",
            headers=self._headers(self.other_token),
        )
        updated_payload = self._profile_payload()
        updated_payload["risk_profile"] = "moderate"
        updated = self.client.put(
            "/api/insights/profile",
            params={"user_id": self.other_user.id},
            json=updated_payload,
            headers=self._headers(self.token),
        )

        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["onboarding_completed"])
        self.assertNotIn("user_id", created.json())
        self.assertEqual(duplicate.status_code, 409)
        self.assertFalse(other_profile.json()["onboarding_completed"])
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["risk_profile"], "moderate")

    def test_profile_rejects_user_id_in_payload(self) -> None:
        payload = self._profile_payload()
        payload["user_id"] = self.other_user.id

        response = self.client.post(
            "/api/insights/profile",
            json=payload,
            headers=self._headers(self.token),
        )

        self.assertEqual(response.status_code, 422)

    def test_analysis_calculates_transactions_categories_and_goals(self) -> None:
        self._create_profile(self.token)
        today = date.today()
        previous_month = self._previous_month_date(today)
        with self.session_factory() as db:
            food = Category(name="Alimentação", type="expense", user_id=self.user.id)
            salary = Category(name="Salário", type="income", user_id=self.user.id)
            db.add_all([food, salary])
            db.commit()
            self._transaction(
                db,
                user_id=self.user.id,
                transaction_type="income",
                amount="2000.00",
                description="Salário",
                transaction_date=today,
                category_id=salary.id,
            )
            self._transaction(
                db,
                user_id=self.user.id,
                transaction_type="expense",
                amount="600.00",
                description="Mercado",
                transaction_date=today,
                category_id=food.id,
            )
            self._transaction(
                db,
                user_id=self.user.id,
                transaction_type="expense",
                amount="300.00",
                description="Mercado anterior",
                transaction_date=previous_month,
                category_id=food.id,
            )
            self._transaction(
                db,
                user_id=self.other_user.id,
                transaction_type="income",
                amount="99999.00",
                description="Outro usuário",
                transaction_date=today,
            )
            goal = Goal(
                user_id=self.user.id,
                name="Reserva",
                target_amount=Decimal("1000.00"),
                current_amount=Decimal("300.00"),
                target_date=None,
                status="active",
            )
            db.add(goal)
            db.commit()
            db.add_all(
                [
                    GoalContribution(
                        user_id=self.user.id,
                        goal_id=goal.id,
                        amount=Decimal("100.00"),
                        source="dashboard",
                    ),
                    GoalContribution(
                        user_id=self.user.id,
                        goal_id=goal.id,
                        amount=Decimal("200.00"),
                        source="whatsapp_text",
                    ),
                ]
            )
            db.commit()

        ai_content = self._ai_content()
        with patch(
            "backend.services.insights_service.generate_ai_insights",
            return_value=ai_content,
        ) as ai_mock:
            response = self.client.get(
                "/api/insights",
                headers=self._headers(self.token),
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        summary = body["summary"]
        self.assertEqual(summary["balance"], 1100.0)
        self.assertEqual(summary["current_month_income"], 2000.0)
        self.assertEqual(summary["current_month_expenses"], 600.0)
        self.assertEqual(summary["free_amount"], 1400.0)
        self.assertEqual(summary["committed_income_percentage"], 30.0)
        self.assertEqual(summary["top_expense_category"], "Alimentação")
        self.assertEqual(summary["expense_change_percentage"], 100.0)
        self.assertEqual(summary["active_goals_count"], 1)
        self.assertEqual(summary["total_saved_in_goals"], 300.0)
        self.assertEqual(summary["total_remaining_in_goals"], 700.0)
        self.assertEqual(summary["average_goal_contribution"], 150.0)
        self.assertEqual(body["market"]["available"], False)
        self.assertEqual(body["ai"]["content"]["financial_summary"], "Resumo")
        ai_mock.assert_called_once()

    def test_ai_cache_avoids_repeated_groq_calls(self) -> None:
        self._create_profile(self.token)
        with patch(
            "backend.services.insights_service.generate_ai_insights",
            return_value=self._ai_content(),
        ) as ai_mock:
            first = self.client.get(
                "/api/insights",
                headers=self._headers(self.token),
            )
            second = self.client.get(
                "/api/insights",
                headers=self._headers(self.token),
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first.json()["ai"]["cached"])
        self.assertTrue(second.json()["ai"]["cached"])
        ai_mock.assert_called_once()

    def test_no_transactions_no_goals_and_groq_unavailable_are_safe(self) -> None:
        self._create_profile(self.token)
        with patch(
            "backend.services.insights_service.generate_ai_insights",
            side_effect=InsightsAIServiceError("offline"),
        ):
            response = self.client.get(
                "/api/insights",
                headers=self._headers(self.token),
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["summary"]["balance"], 0.0)
        self.assertEqual(body["summary"]["transaction_count"], 0)
        self.assertIsNone(body["summary"]["committed_income_percentage"])
        self.assertIsNone(body["summary"]["average_monthly_expenses"])
        self.assertEqual(body["summary"]["active_goals_count"], 0)
        self.assertFalse(body["ai"]["available"])
        self.assertIsNotNone(body["ai"]["message"])
        self.assertEqual(body["health"]["level"], "attention")

    def test_zero_income_and_zero_previous_expense_do_not_divide_by_zero(self) -> None:
        with self.session_factory() as db:
            self._transaction(
                db,
                user_id=self.user.id,
                transaction_type="expense",
                amount="50.00",
                description="Despesa",
                transaction_date=date.today(),
            )
            summary = calculate_financial_summary(
                db,
                user_id=self.user.id,
                current_date=date.today(),
            )

        self.assertIsNone(summary.committed_income_percentage)
        self.assertIsNone(summary.expense_change_percentage)
        self.assertIsNone(summary.estimated_monthly_savings_capacity)

    def test_analysis_requires_completed_profile(self) -> None:
        response = self.client.get(
            "/api/insights",
            headers=self._headers(self.token),
        )
        summary = self.client.get(
            "/api/insights/summary",
            headers=self._headers(self.token),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(summary.status_code, 200)
        self.assertFalse(summary.json()["onboarding_completed"])

    def _create_profile(self, token: str):
        return self.client.post(
            "/api/insights/profile",
            json=self._profile_payload(),
            headers=self._headers(token),
        )

    @staticmethod
    def _profile_payload() -> dict:
        return {
            "main_goal": "emergency_reserve",
            "investment_horizon": "one_to_three_years",
            "risk_profile": "conservative",
            "liquidity_need": "high",
            "has_debts": False,
            "income_type": "fixed",
            "main_priority": "increase_savings",
        }

    @staticmethod
    def _ai_content() -> AIInsightsContent:
        return AIInsightsContent(
            financial_summary="Resumo",
            positive_points=["Ponto positivo"],
            attention_points=["Ponto de atenção"],
            improvements=["Melhoria"],
            cut_suggestions=["Corte"],
            prioritization="Prioridade",
            goals_analysis="Metas",
            next_steps=["Passo 1", "Passo 2", "Passo 3"],
        )

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _user(db: Session, email: str, phone: str) -> User:
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

    @staticmethod
    def _transaction(
        db: Session,
        *,
        user_id: int,
        transaction_type: str,
        amount: str,
        description: str,
        transaction_date: date,
        category_id: int | None = None,
    ) -> None:
        db.add(
            FinancialTransaction(
                user_id=user_id,
                type=transaction_type,
                amount=Decimal(amount),
                description=description,
                category_id=category_id,
                transaction_date=transaction_date,
                source="dashboard_manual",
            )
        )
        db.commit()

    @staticmethod
    def _previous_month_date(value: date) -> date:
        if value.month == 1:
            return date(value.year - 1, 12, 15)
        return date(value.year, value.month - 1, 15)


if __name__ == "__main__":
    unittest.main()
