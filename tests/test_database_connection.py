import unittest

from backend.database.connection import normalize_database_url


class DatabaseConnectionTestCase(unittest.TestCase):
    def test_normalizes_railway_postgresql_url_for_psycopg_3(self) -> None:
        normalized_url = normalize_database_url(
            "postgresql://localhost/database"
        )

        self.assertEqual(
            normalized_url,
            "postgresql+psycopg://localhost/database",
        )

    def test_keeps_an_already_compatible_url(self) -> None:
        compatible_url = "postgresql+psycopg://localhost/database"

        self.assertEqual(normalize_database_url(compatible_url), compatible_url)


if __name__ == "__main__":
    unittest.main()
