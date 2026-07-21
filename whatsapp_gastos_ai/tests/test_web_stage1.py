from __future__ import annotations

import unittest
import os
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.web.routes import api_router, page_router
from backend.services.web_auth_service import WebUser


def _user() -> WebUser:
    return WebUser(
        id=1,
        nome="Admin Fincontrol",
        telefone="5511999999999",
        email="admin@fincontrol.local",
        schema_user="schema_fin",
        autorizado=True,
        web_active=True,
        web_role="admin",
        web_avatar_url=None,
    )


class WebStage1Test(unittest.TestCase):
    def setUp(self) -> None:
        self._env_patch = patch.dict(
            os.environ,
            {
                "WEB_ADMIN_NAME": "",
                "WEB_ADMIN_PHONE": "",
                "WEB_ADMIN_EMAIL": "",
                "WEB_ADMIN_PASSWORD": "",
            },
            clear=False,
        )
        self._env_patch.start()
        app = FastAPI()
        app.include_router(api_router)
        app.include_router(page_router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._env_patch.stop()

    def test_login_sets_cookies_and_returns_user(self) -> None:
        fake_result = {
            "user": _user(),
            "access_token": "access.token",
            "refresh_token": "refresh.token",
            "session_id": "session-id",
            "expires_in": 3600,
            "refresh_expires_in": 604800,
        }
        with patch("backend.web.routes.authenticate_web_user", return_value=fake_result):
            response = self.client.post(
                "/api/auth/login",
                json={"identifier": "admin@fincontrol.local", "password": "senha123", "remember_me": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertIn("fc_access_token", response.cookies)
        self.assertIn("fc_refresh_token", response.cookies)

    def test_me_requires_authentication(self) -> None:
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_me_returns_current_user_when_authenticated(self) -> None:
        with patch("backend.web.routes.get_user_from_access_token", return_value=_user()):
            self.client.cookies.set("fc_access_token", "access.token")
            response = self.client.get("/api/auth/me")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(response.json()["data"]["user"]["email"], "admin@fincontrol.local")

    def test_dashboard_summary_uses_real_snapshot_contract(self) -> None:
        fake_snapshot = {
            "user": {"id": 1, "name": "Admin", "email": "admin@fincontrol.local"},
            "period": {"value": "current_month", "label": "07/2026"},
            "cards": {"balance": {"value": 1200.0, "comparison": 5.0}, "income": {"value": 2500.0}, "expense": {"value": 1300.0}, "pending_invoice": {"value": 0.0}},
            "charts": {"categories": [{"label": "Mercado", "value": 300.0, "color": "#1b7a43"}], "cash_flow": {"labels": ["01/07"], "income": [100.0], "expense": [50.0]}},
            "recent_transactions": [{"description": "Almoço", "amount": 35.0}],
            "reminders": [{"message": "Pagar internet"}],
            "goals": [],
            "ai_summary": {"title": "Resumo", "text": "Tudo certo", "highlights": ["Entradas: R$ 2.500,00"]},
        }
        with patch("backend.web.routes.get_user_from_access_token", return_value=_user()), patch(
            "backend.web.routes.build_dashboard_snapshot",
            return_value=fake_snapshot,
        ):
            self.client.cookies.set("fc_access_token", "access.token")
            response = self.client.get("/api/dashboard/summary")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(response.json()["data"]["period"]["value"], "current_month")

    def test_dashboard_sections_return_payloads(self) -> None:
        with patch("backend.web.routes.get_user_from_access_token", return_value=_user()), patch(
            "backend.web.routes.build_dashboard_section",
            return_value={"success": True, "data": [{"label": "Mercado"}], "message": None},
        ):
            self.client.cookies.set("fc_access_token", "access.token")
            response = self.client.get("/api/dashboard/categories")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["label"], "Mercado")

    def test_login_and_dashboard_pages_exist(self) -> None:
        response_login = self.client.get("/login")
        response_dashboard = self.client.get("/dashboard")
        self.assertEqual(response_login.status_code, 200)
        self.assertEqual(response_dashboard.status_code, 200)


if __name__ == "__main__":
    unittest.main()
