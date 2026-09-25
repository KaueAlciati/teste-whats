import hashlib
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.base import Base
from backend.database.connection import get_db
from backend.main import app
from backend.models import PasswordResetToken, User  # noqa: F401
from backend.services.email_service import (
    RESEND_EMAILS_URL,
    RESEND_TIMEOUT_SECONDS,
    EmailDeliveryError,
    ResendSettings,
    send_password_reset_email,
    send_password_reset_email_safely,
)


GENERIC_MESSAGE = (
    "Se o e-mail estiver cadastrado, você receberá um link de recuperação."
)


class PasswordResetApiTestCase(unittest.TestCase):
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
                "PASSWORD_RESET_EXPIRE_MINUTES": "30",
                "FRONTEND_URL": "https://fincontrol.example",
                "RESEND_API_KEY": "re_test-secret",
                "RESEND_FROM_EMAIL": "contato@fincontrol.example",
            },
            clear=False,
        )
        self.environment.start()
        self.client = TestClient(app)
        self._register()

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        self.environment.stop()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_forgot_password_stores_only_hash_and_queues_email(self) -> None:
        with patch(
            "backend.api.auth.send_password_reset_email_safely"
        ) as email_mock:
            response = self._forgot("KAUE@EXAMPLE.COM")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": GENERIC_MESSAGE})
        email_mock.assert_called_once()
        recipient, raw_token, _settings = email_mock.call_args.args
        self.assertEqual(recipient, "kaue@example.com")
        self.assertGreaterEqual(len(raw_token), 40)
        self.assertIsInstance(_settings, ResendSettings)

        with self.session_factory() as db:
            stored = db.scalar(select(PasswordResetToken))
            self.assertIsNotNone(stored)
            self.assertNotEqual(stored.token_hash, raw_token)
            self.assertEqual(
                stored.token_hash,
                hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            )

    def test_unknown_email_returns_same_response_without_creating_token(self) -> None:
        with patch(
            "backend.api.auth.send_password_reset_email_safely"
        ) as email_mock:
            known_response = self._forgot("kaue@example.com")
            unknown_response = self._forgot("desconhecido@example.com")

        self.assertEqual(unknown_response.status_code, known_response.status_code)
        self.assertEqual(unknown_response.json(), known_response.json())
        self.assertEqual(unknown_response.json(), {"message": GENERIC_MESSAGE})
        self.assertEqual(email_mock.call_count, 1)
        with self.session_factory() as db:
            self.assertEqual(
                db.scalar(select(func.count(PasswordResetToken.id))),
                1,
            )

    def test_valid_token_changes_argon2_password_and_is_single_use(self) -> None:
        token = self._request_token()

        reset = self._reset(token, "nova-senha-456")

        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json(), {"status": "ok"})
        old_login = self._login("senha-segura-123")
        new_login = self._login("nova-senha-456")
        self.assertEqual(old_login.status_code, 401)
        self.assertEqual(new_login.status_code, 200)
        with self.session_factory() as db:
            user = db.scalar(select(User).where(User.email == "kaue@example.com"))
            stored = db.scalar(select(PasswordResetToken))
            self.assertTrue(user.password_hash.startswith("$argon2"))
            self.assertIsNotNone(stored.used_at)

        reused = self._reset(token, "outra-senha-789")
        self.assertEqual(reused.status_code, 400)
        self.assertEqual(
            reused.json()["detail"],
            "Token de recuperação inválido ou expirado",
        )

    def test_expired_token_is_rejected(self) -> None:
        token = self._request_token()
        with self.session_factory() as db:
            stored = db.scalar(select(PasswordResetToken))
            stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()

        response = self._reset(token, "nova-senha-456")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._login("senha-segura-123").status_code, 200)

    def test_new_request_invalidates_previous_token(self) -> None:
        first_token = self._request_token()
        second_token = self._request_token()

        self.assertNotEqual(first_token, second_token)
        self.assertEqual(self._reset(first_token, "nova-senha-456").status_code, 400)
        self.assertEqual(self._reset(second_token, "nova-senha-456").status_code, 200)

    def test_password_confirmation_must_match(self) -> None:
        token = self._request_token()
        response = self.client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "new_password": "nova-senha-456",
                "confirm_new_password": "senha-diferente-789",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_invalid_token_is_rejected(self) -> None:
        response = self._reset("x" * 64, "nova-senha-456")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Token de recuperação inválido ou expirado",
        )

    def _register(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={
                "name": "Kaue Alciati",
                "email": "kaue@example.com",
                "whatsapp_phone": "5515999999999",
                "password": "senha-segura-123",
            },
        )
        self.assertEqual(response.status_code, 201)

    def _forgot(self, email: str):
        return self.client.post(
            "/api/auth/forgot-password",
            json={"email": email},
        )

    def _request_token(self) -> str:
        with patch(
            "backend.api.auth.send_password_reset_email_safely"
        ) as email_mock:
            response = self._forgot("kaue@example.com")
        self.assertEqual(response.status_code, 200)
        return email_mock.call_args.args[1]

    def _reset(self, token: str, password: str):
        return self.client.post(
            "/api/auth/reset-password",
            json={
                "token": token,
                "new_password": password,
                "confirm_new_password": password,
            },
        )

    def _login(self, password: str):
        return self.client.post(
            "/api/auth/login",
            json={"email": "kaue@example.com", "password": password},
        )


class PasswordResetEmailTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = ResendSettings(
            api_key="re_test-secret",
            from_email="contato@fincontrol.example",
            frontend_url="https://fincontrol.example",
        )

    def test_email_posts_to_resend_and_contains_frontend_link(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None

        with patch(
            "backend.services.email_service.httpx.post",
            return_value=response,
        ) as post_mock:
            send_password_reset_email(
                "kaue@example.com",
                "secure-token",
                settings=self.settings,
            )

        post_mock.assert_called_once()
        args, kwargs = post_mock.call_args
        self.assertEqual(args, (RESEND_EMAILS_URL,))
        self.assertEqual(kwargs["timeout"], RESEND_TIMEOUT_SECONDS)
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer re_test-secret",
        )
        payload = kwargs["json"]
        self.assertEqual(
            payload["subject"],
            "Recuperação de senha — FinControl AI",
        )
        self.assertEqual(
            payload["from"],
            "FinControl AI <contato@fincontrol.example>",
        )
        self.assertEqual(payload["to"], ["kaue@example.com"])
        self.assertIn(
            "https://fincontrol.example/reset-password?token=secure-token",
            payload["text"],
        )
        self.assertIn("FinControl AI", payload["html"])
        self.assertIn("expira", payload["text"])
        self.assertIn("ignore", payload["text"])
        self.assertNotIn("re_test-secret", str(payload))
        response.raise_for_status.assert_called_once_with()

    def test_resend_error_raises_delivery_error(self) -> None:
        request = httpx.Request("POST", RESEND_EMAILS_URL)
        response = Mock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Resend rejected the request",
            request=request,
            response=httpx.Response(422, request=request),
        )

        with patch(
            "backend.services.email_service.httpx.post",
            return_value=response,
        ):
            with self.assertRaisesRegex(
                EmailDeliveryError,
                "Não foi possível enviar o e-mail",
            ):
                send_password_reset_email(
                    "kaue@example.com",
                    "secure-token",
                    settings=self.settings,
                )

    def test_resend_timeout_raises_delivery_error(self) -> None:
        with patch(
            "backend.services.email_service.httpx.post",
            side_effect=httpx.TimeoutException("timeout"),
        ):
            with self.assertRaises(EmailDeliveryError):
                send_password_reset_email(
                    "kaue@example.com",
                    "secure-token",
                    settings=self.settings,
                )

    def test_safe_delivery_does_not_log_recovery_token(self) -> None:
        token = "secret-recovery-token-that-must-not-be-logged"
        with patch(
            "backend.services.email_service.send_password_reset_email",
            side_effect=EmailDeliveryError("delivery failed"),
        ):
            with self.assertLogs("uvicorn.error", level="ERROR") as captured:
                send_password_reset_email_safely(
                    "kaue@example.com",
                    token,
                    self.settings,
                )

        logs = "\n".join(captured.output)
        self.assertNotIn(token, logs)
        self.assertNotIn(self.settings.api_key, logs)
        self.assertIn("EmailDeliveryError", logs)


if __name__ == "__main__":
    unittest.main()
