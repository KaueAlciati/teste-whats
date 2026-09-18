import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.database.base import Base
from backend.models import Category, FinancialTransaction, User  # noqa: F401
from backend.services.user_service import (
    get_or_create_whatsapp_user,
    normalize_whatsapp_phone,
)


class UserServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine, expire_on_commit=False)()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_normalize_whatsapp_phone_keeps_only_digits(self) -> None:
        normalized = normalize_whatsapp_phone("+55 (15) 99999-9999")
        self.assertEqual(normalized, "5515999999999")

    def test_get_or_create_creates_user(self) -> None:
        user = get_or_create_whatsapp_user(
            self.session,
            "+55 (15) 99999-9999",
        )

        self.assertIsNotNone(user.id)
        self.assertEqual(user.whatsapp_phone, "5515999999999")
        self.assertTrue(user.active)

    def test_existing_user_is_not_duplicated(self) -> None:
        first_user = get_or_create_whatsapp_user(
            self.session,
            "5515999999999",
        )
        second_user = get_or_create_whatsapp_user(
            self.session,
            "+55 (15) 99999-9999",
        )

        user_count = self.session.scalar(select(func.count(User.id)))
        self.assertEqual(first_user.id, second_user.id)
        self.assertEqual(user_count, 1)


if __name__ == "__main__":
    unittest.main()
