import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.api.webhook as webhook
from backend.database.base import Base
from backend.main import app
from backend.models import User
from backend.services.user_service import authorize_registered_whatsapp_user


class WhatsAppAccessControlTestCase(unittest.TestCase):
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
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_registered_user_message_is_processed(self) -> None:
        self._create_user(whatsapp_verified=True)
        process_mock = AsyncMock(return_value=None)

        with self._patch_access(), patch.object(
            webhook,
            "process_financial_message",
            process_mock,
        ):
            response = self.client.post("/webhook", json=self._text_payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        process_mock.assert_awaited_once_with(
            "5515999999999",
            "wamid.access-test",
            "gastei 10 reais de chocolate",
        )

    def test_first_message_marks_whatsapp_as_verified(self) -> None:
        self._create_user(whatsapp_verified=False)
        process_mock = AsyncMock(return_value=None)

        with self._patch_access(), patch.object(
            webhook,
            "process_financial_message",
            process_mock,
        ):
            response = self.client.post("/webhook", json=self._text_payload())

        self.assertEqual(response.status_code, 200)
        process_mock.assert_awaited_once()
        with self.session_factory() as db:
            user = db.scalar(
                select(User).where(User.whatsapp_phone == "5515999999999")
            )
            self.assertIsNotNone(user)
            self.assertTrue(user.whatsapp_verified)

    def test_unknown_number_is_ignored_without_creating_user(self) -> None:
        process_mock = AsyncMock(return_value=None)

        with self._patch_access(), patch.object(
            webhook,
            "process_financial_message",
            process_mock,
        ):
            response = self.client.post("/webhook", json=self._text_payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        process_mock.assert_not_awaited()
        with self.session_factory() as db:
            self.assertEqual(db.scalar(select(func.count(User.id))), 0)

    def test_inactive_user_is_ignored(self) -> None:
        self._create_user(active=False, whatsapp_verified=False)
        process_mock = AsyncMock(return_value=None)

        with self._patch_access(), patch.object(
            webhook,
            "process_financial_message",
            process_mock,
        ):
            response = self.client.post("/webhook", json=self._text_payload())

        self.assertEqual(response.status_code, 200)
        process_mock.assert_not_awaited()
        with self.session_factory() as db:
            user = db.scalar(select(User))
            self.assertIsNotNone(user)
            self.assertFalse(user.whatsapp_verified)

    def _patch_access(self):
        def authorize(whatsapp_phone: str) -> bool:
            with self.session_factory() as db:
                return (
                    authorize_registered_whatsapp_user(db, whatsapp_phone)
                    is not None
                )

        return patch.object(
            webhook,
            "authorize_registered_whatsapp_phone",
            side_effect=authorize,
        )

    def _create_user(
        self,
        *,
        active: bool = True,
        whatsapp_verified: bool = False,
    ) -> None:
        with self.session_factory() as db:
            db.add(
                User(
                    name="Usuário teste",
                    email="usuario@example.com",
                    whatsapp_phone="5515999999999",
                    password_hash="$argon2id$test-hash",
                    active=active,
                    whatsapp_verified=whatsapp_verified,
                )
            )
            db.commit()

    @staticmethod
    def _text_payload() -> dict:
        return {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "5511000000000"
                                },
                                "messages": [
                                    {
                                        "from": "+55 (15) 99999-9999",
                                        "id": "wamid.access-test",
                                        "type": "text",
                                        "text": {
                                            "body": "gastei 10 reais de chocolate"
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }


if __name__ == "__main__":
    unittest.main()
