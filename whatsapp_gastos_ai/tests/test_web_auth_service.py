from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.services import web_auth_service as auth


class FakeCursor:
    def __init__(self, responses: list[object] | None = None):
        self.responses = list(responses or [])
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []
        self.closed = False

    def execute(self, sql: str, params: tuple[object, ...] | None = None):
        self.executed.append((sql, params))

    def fetchone(self):
        if not self.responses:
            return None
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def fetchall(self):
        if not self.responses:
            return []
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class WebAuthServiceTest(unittest.TestCase):
    def test_normalize_phone_accepts_brazilian_formats(self):
        self.assertEqual(auth.normalize_phone_number("15992013795"), "5515992013795")
        self.assertEqual(auth.normalize_phone_number("(15) 99201-3795"), "5515992013795")
        self.assertEqual(auth.normalize_phone_number("+55 15 99201-3795"), "5515992013795")
        self.assertEqual(auth.normalize_phone_number("5515992013795"), "5515992013795")

    def test_register_commits_and_persists_hash(self):
        cursor = FakeCursor(
            [
                None,
                (42,),
                None,
                (42, "Kaue", "5515992013795", "email@exemplo.com", "user_42", True, True, "user", None, False, False, True, None, None, None),
            ]
        )
        conn = FakeConn(cursor)

        with patch("backend.services.web_auth_service.conectar_bd", return_value=conn), patch(
            "backend.services.web_auth_service.fetch_user_by_id",
            return_value=auth.WebUser(
                id=42,
                nome="Kaue",
                telefone="5515992013795",
                email="email@exemplo.com",
                schema_user="user_42",
                autorizado=True,
                web_active=True,
                web_role="user",
                web_avatar_url=None,
                is_active=True,
            ),
        ):
            user = auth.register_web_user("Kaue", "Email@Exemplo.com", "(15) 99201-3795", "senha-segura")

        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)
        self.assertEqual(user.id, 42)
        insert_sql, insert_params = cursor.executed[1]
        self.assertIn("INSERT INTO usuarios", insert_sql)
        self.assertEqual(insert_params[2], "email@exemplo.com")
        self.assertEqual(insert_params[3], "5515992013795")
        self.assertNotEqual(insert_params[5], "senha-segura")

    def test_register_rejects_duplicate_email_or_phone(self):
        cursor = FakeCursor([(1,)])
        conn = FakeConn(cursor)

        with patch("backend.services.web_auth_service.conectar_bd", return_value=conn):
            with self.assertRaises(ValueError):
                auth.register_web_user("Kaue", "email@exemplo.com", "15992013795", "senha-segura")

        self.assertFalse(conn.committed)
        self.assertTrue(conn.rolled_back)
        self.assertTrue(conn.closed)

    def test_fetch_user_by_identifier_normalizes_email_and_phone(self):
        cursor = FakeCursor(
            [
                (7, "Kaue", "5515992013795", "email@exemplo.com", "user_7", True, True, "user", None, False, False, True, None, None, None)
            ]
        )
        conn = FakeConn(cursor)

        with patch("backend.services.web_auth_service.conectar_bd", return_value=conn):
            user = auth.fetch_user_by_identifier("  EMAIL@EXEMPLO.COM  ")

        self.assertIsNotNone(user)
        self.assertEqual(cursor.executed[0][1][1], "email@exemplo.com")

    def test_fetch_user_by_identifier_accepts_phone_variants(self):
        for identifier, expected_phone in [
            ("15992013795", "5515992013795"),
            ("5515992013795", "5515992013795"),
            ("+55 15 99201-3795", "5515992013795"),
        ]:
            with self.subTest(identifier=identifier):
                cursor = FakeCursor(
                    [
                        (8, "Kaue", expected_phone, "email@exemplo.com", "user_8", True, True, "user", None, False, False, True, None, None, None)
                    ]
                )
                conn = FakeConn(cursor)
                with patch("backend.services.web_auth_service.conectar_bd", return_value=conn):
                    user = auth.fetch_user_by_identifier(identifier)
                self.assertIsNotNone(user)
                self.assertEqual(cursor.executed[0][1][0], expected_phone)

    def test_authenticate_web_user_accepts_bcrypt_hash_without_salt(self):
        password_hash = auth.hash_password("senha-segura")
        user = auth.WebUser(
            id=99,
            nome="Kaue",
            telefone="5515992013795",
            email="email@exemplo.com",
            schema_user="user_99",
            autorizado=True,
            web_active=True,
            web_role="user",
            web_avatar_url=None,
            is_active=True,
        )
        cursor = FakeCursor([(password_hash, None, True)])
        conn = FakeConn(cursor)

        with patch("backend.services.web_auth_service.fetch_user_by_identifier", return_value=user), patch(
            "backend.services.web_auth_service.conectar_bd", return_value=conn
        ), patch(
            "backend.services.web_auth_service.create_session_tokens",
            return_value={
                "access_token": "access",
                "refresh_token": "refresh",
                "session_id": "session",
                "expires_in": 3600,
                "refresh_expires_in": 7200,
            },
        ):
            result = auth.authenticate_web_user("email@exemplo.com", "senha-segura")

        self.assertEqual(result["user"].id, 99)
        self.assertTrue(conn.closed)
        self.assertTrue(auth.verify_password("senha-segura", password_hash))

    def test_authenticate_web_user_rejects_wrong_password_and_inactive_user(self):
        password_hash = auth.hash_password("senha-segura")
        active_user = auth.WebUser(
            id=100,
            nome="Kaue",
            telefone="5515992013795",
            email="email@exemplo.com",
            schema_user="user_100",
            autorizado=True,
            web_active=True,
            web_role="user",
            web_avatar_url=None,
            is_active=True,
        )
        inactive_user = auth.WebUser(
            id=101,
            nome="Kaue",
            telefone="5515992013795",
            email="email@exemplo.com",
            schema_user="user_101",
            autorizado=True,
            web_active=False,
            web_role="user",
            web_avatar_url=None,
            is_active=False,
        )

        cursor = FakeCursor([(password_hash, None, True)])
        conn = FakeConn(cursor)

        with patch("backend.services.web_auth_service.fetch_user_by_identifier", return_value=active_user), patch(
            "backend.services.web_auth_service.conectar_bd", return_value=conn
        ), patch(
            "backend.services.web_auth_service.create_session_tokens",
            return_value={
                "access_token": "access",
                "refresh_token": "refresh",
                "session_id": "session",
                "expires_in": 3600,
                "refresh_expires_in": 7200,
            },
        ):
            with self.assertRaises(ValueError):
                auth.authenticate_web_user("email@exemplo.com", "senha-errada")

        with patch("backend.services.web_auth_service.fetch_user_by_identifier", return_value=inactive_user), patch(
            "backend.services.web_auth_service.create_session_tokens",
            return_value={
                "access_token": "access",
                "refresh_token": "refresh",
                "session_id": "session",
                "expires_in": 3600,
                "refresh_expires_in": 7200,
            },
        ):
            with self.assertRaises(ValueError):
                auth.authenticate_web_user("email@exemplo.com", "senha-segura")

    def test_auth_debug_summary_is_disabled_by_default(self):
        with self.assertRaises(ValueError):
            auth.auth_debug_summary(email="email@exemplo.com")


if __name__ == "__main__":
    unittest.main()
