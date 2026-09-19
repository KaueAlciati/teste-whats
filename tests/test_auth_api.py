import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.base import Base
from backend.database.connection import get_db
from backend.main import app
from backend.models import User  # noqa: F401
from backend.services.user_service import get_or_create_whatsapp_user


class AuthApiTestCase(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.environment.stop()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_register_normalizes_data_and_hashes_password(self) -> None:
        response = self._register()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["email"], "kaue@example.com")
        self.assertEqual(body["whatsapp_phone"], "5515999999999")
        self.assertFalse(body["whatsapp_verified"])
        self.assertNotIn("password", body)

        with self.session_factory() as db:
            user = db.scalar(select(User).where(User.id == body["id"]))
            self.assertIsNotNone(user)
            self.assertNotEqual(user.password_hash, "senha-segura-123")
            self.assertTrue(user.password_hash.startswith("$argon2"))

    def test_register_upgrades_existing_whatsapp_user(self) -> None:
        with self.session_factory() as db:
            existing = get_or_create_whatsapp_user(db, "5515999999999")
            existing_id = existing.id

        response = self._register()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], existing_id)
        with self.session_factory() as db:
            self.assertEqual(len(db.scalars(select(User)).all()), 1)

    def test_login_returns_access_token_and_me_returns_user(self) -> None:
        self._register()

        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "KAUE@EXAMPLE.COM",
                "password": "senha-segura-123",
            },
        )

        self.assertEqual(login.status_code, 200)
        token = login.json()["access_token"]
        self.assertEqual(login.json()["token_type"], "bearer")
        self.assertGreater(len(token), 40)

        me = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "kaue@example.com")

    def test_duplicate_email_is_rejected(self) -> None:
        self._register()
        response = self._register(
            email="KAUE@example.com",
            phone="5515888888888",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "E-mail já cadastrado")

    def test_duplicate_phone_is_rejected(self) -> None:
        self._register()
        response = self._register(
            email="outro@example.com",
            phone="+55 (15) 99999-9999",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "WhatsApp já cadastrado")

    def test_wrong_password_is_rejected(self) -> None:
        self._register()
        response = self.client.post(
            "/api/auth/login",
            json={
                "email": "kaue@example.com",
                "password": "senha-incorreta",
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_me_without_token_is_rejected(self) -> None:
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_cors_allows_local_frontend(self) -> None:
        response = self.client.options(
            "/api/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:3000",
        )

    def _register(
        self,
        *,
        email: str = "Kaue@Example.com",
        phone: str = "+55 (15) 99999-9999",
    ):
        return self.client.post(
            "/api/auth/register",
            json={
                "name": "  Kaue   Alciati  ",
                "email": email,
                "whatsapp_phone": phone,
                "password": "senha-segura-123",
            },
        )


if __name__ == "__main__":
    unittest.main()
