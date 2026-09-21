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
from backend.models import Goal, User
from backend.services.auth_service import create_access_token


class GoalsApiTestCase(unittest.TestCase):
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

    def test_create_and_list_use_authenticated_user(self) -> None:
        created = self._create(self.token, name="Reserva")
        self._create(self.other_token, name="Meta de outro usuário")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["goal_name"], "Reserva")
        self.assertEqual(created.json()["current"], 0.0)
        self.assertEqual(created.json()["percent"], 0.0)

        listed = self.client.get(
            "/api/goals",
            params={"user_id": self.other_user.id},
            headers=self._headers(self.token),
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["goal_name"], "Reserva")

        with self.session_factory() as db:
            goal = db.scalar(
                select(Goal).where(Goal.id == created.json()["id"])
            )
            self.assertIsNotNone(goal)
            self.assertEqual(goal.user_id, self.user.id)
            self.assertEqual(goal.status, "active")

    def test_create_rejects_user_id_from_client(self) -> None:
        payload = self._payload("Reserva")
        payload["user_id"] = self.other_user.id

        response = self.client.post(
            "/api/goals",
            json=payload,
            headers=self._headers(self.token),
        )

        self.assertEqual(response.status_code, 422)

    def test_edit_deposit_and_complete_goal(self) -> None:
        goal_id = self._create(self.token, name="Reserva").json()["id"]

        edited = self.client.put(
            f"/api/goals/{goal_id}",
            json={
                "name": "Reserva de emergência",
                "target_amount": 2000,
                "target_date": "2027-12-31",
            },
            headers=self._headers(self.token),
        )
        deposited = self.client.put(
            f"/api/goals/{goal_id}",
            json={"current_amount_delta": 500},
            headers=self._headers(self.token),
        )
        completed = self.client.put(
            f"/api/goals/{goal_id}",
            json={"status": "completed"},
            headers=self._headers(self.token),
        )

        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["goal_name"], "Reserva de emergência")
        self.assertEqual(edited.json()["target"], 2000.0)
        self.assertEqual(deposited.json()["current"], 500.0)
        self.assertEqual(deposited.json()["percent"], 25.0)
        self.assertTrue(completed.json()["completed"])
        self.assertEqual(completed.json()["current"], 2000.0)
        self.assertEqual(completed.json()["percent"], 100.0)

    def test_user_cannot_update_or_delete_another_users_goal(self) -> None:
        goal_id = self._create(self.other_token, name="Outra meta").json()["id"]

        update = self.client.put(
            f"/api/goals/{goal_id}",
            json={"name": "Tentativa indevida"},
            headers=self._headers(self.token),
        )
        delete = self.client.delete(
            f"/api/goals/{goal_id}",
            headers=self._headers(self.token),
        )

        self.assertEqual(update.status_code, 404)
        self.assertEqual(delete.status_code, 404)
        with self.session_factory() as db:
            self.assertIsNotNone(db.get(Goal, goal_id))

    def test_delete_owned_goal(self) -> None:
        goal_id = self._create(self.token, name="Reserva").json()["id"]

        response = self.client.delete(
            f"/api/goals/{goal_id}",
            headers=self._headers(self.token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        with self.session_factory() as db:
            self.assertIsNone(db.get(Goal, goal_id))

    def test_goals_require_authentication(self) -> None:
        response = self.client.get("/api/goals")

        self.assertEqual(response.status_code, 401)

    def _create(self, token: str, *, name: str):
        return self.client.post(
            "/api/goals",
            json=self._payload(name),
            headers=self._headers(token),
        )

    @staticmethod
    def _payload(name: str) -> dict:
        return {
            "name": name,
            "target_amount": 1000,
            "target_date": "2027-06-30",
        }

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _user(db, email: str, phone: str) -> User:
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
