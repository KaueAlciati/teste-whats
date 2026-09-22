import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.base import Base
from backend.database.connection import get_db
from backend.main import app
from backend.models import FinancialTransaction, User
from backend.services.auth_service import create_access_token


class StatementImportApiTestCase(unittest.TestCase):
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
            self.user = self._user(
                db,
                email="import@example.com",
                phone="5515999999999",
            )
            self.other_user = self._user(
                db,
                email="other-import@example.com",
                phone="5515888888888",
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

    def test_preview_detects_comma_csv_brazilian_values_and_dates(self) -> None:
        response = self._preview(
            "Data,Descrição,Valor,Tipo\n"
            '21/09/2026,POSTO SHELL,"-1.234,56",Débito\n'
            '22/09/2026,Salário,"2.500,00",Crédito\n'
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["delimiter"], ",")
        self.assertFalse(body["mapping_required"])
        self.assertEqual(body["ready"], 2)
        self.assertEqual(body["rows"][0]["date"], "2026-09-21")
        self.assertEqual(body["rows"][0]["amount"], 1234.56)
        self.assertEqual(body["rows"][0]["type"], "expense")
        self.assertEqual(body["rows"][0]["category"], "Transporte")
        self.assertEqual(body["rows"][1]["type"], "income")

    def test_preview_detects_semicolon_csv_and_signs(self) -> None:
        response = self._preview(
            "Data;Histórico;Valor\n"
            "20/09/2026;IFOOD;-40,90\n"
            "21/09/2026;PIX RECEBIDO;+1500,00\n"
        )

        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        self.assertEqual(response.json()["delimiter"], ";")
        self.assertEqual(rows[0]["type"], "expense")
        self.assertEqual(rows[0]["category"], "Alimentação")
        self.assertEqual(rows[1]["type"], "income")

    def test_preview_detects_separate_credit_and_debit_columns(self) -> None:
        response = self._preview(
            "Data;Descrição;Entrada;Saída\n"
            "20/09/2026;Pagamento;900,00;\n"
            "21/09/2026;Mercado;;75,20\n"
        )

        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]
        self.assertEqual(rows[0]["type"], "income")
        self.assertEqual(rows[0]["amount"], 900.0)
        self.assertEqual(rows[1]["type"], "expense")
        self.assertEqual(rows[1]["amount"], 75.2)

    def test_manual_column_mapping_is_requested_and_applied(self) -> None:
        content = (
            "Quando;Texto;Quantia;Natureza\n"
            "19/09/2026;Mercado;50,00;Saída\n"
        )
        automatic = self._preview(content)
        self.assertEqual(automatic.status_code, 200)
        self.assertTrue(automatic.json()["mapping_required"])
        self.assertEqual(automatic.json()["rows"], [])
        self.assertIn("Quando", automatic.json()["columns"])

        mapped = self._preview(
            content,
            mapping={
                "date_column": "Quando",
                "description_column": "Texto",
                "amount_column": "Quantia",
                "type_column": "Natureza",
            },
        )
        self.assertEqual(mapped.status_code, 200)
        self.assertFalse(mapped.json()["mapping_required"])
        self.assertEqual(mapped.json()["rows"][0]["type"], "expense")

    def test_preview_and_cancel_do_not_save_any_transaction(self) -> None:
        response = self._preview(self._valid_csv())
        self.assertEqual(response.status_code, 200)

        with self.session_factory() as db:
            count = db.scalar(select(func.count(FinancialTransaction.id)))
        self.assertEqual(count, 0)

    def test_confirmation_saves_selected_rows_with_import_source(self) -> None:
        row = self._preview(self._valid_csv()).json()["rows"][0]
        confirmed = self._confirm(self.token, row)

        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["imported"], 1)
        listed = self.client.get(
            "/api/transactions",
            headers=self._headers(self.token),
        )
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["source"], "import_csv")
        self.assertEqual(listed.json()[0]["description"], "IFOOD")

    def test_duplicate_requires_explicit_confirmation(self) -> None:
        row = self._preview(self._valid_csv()).json()["rows"][0]
        self.assertEqual(self._confirm(self.token, row).json()["imported"], 1)

        duplicate_preview = self._preview(self._valid_csv()).json()["rows"][0]
        self.assertEqual(duplicate_preview["status"], "possible_duplicate")
        skipped = self._confirm(self.token, duplicate_preview)
        self.assertEqual(skipped.json()["imported"], 0)
        self.assertEqual(skipped.json()["skipped_duplicates"], 1)

        imported = self._confirm(
            self.token,
            duplicate_preview,
            allow_duplicate=True,
        )
        self.assertEqual(imported.json()["imported"], 1)

    def test_import_is_isolated_by_authenticated_user(self) -> None:
        row = self._preview(self._valid_csv(), token=self.other_token).json()["rows"][0]
        self.assertEqual(self._confirm(self.other_token, row).status_code, 200)

        own_preview = self._preview(self._valid_csv(), token=self.token)
        self.assertEqual(own_preview.json()["rows"][0]["status"], "ready")
        own_row = own_preview.json()["rows"][0]
        self.assertEqual(self._confirm(self.token, own_row).status_code, 200)

        with self.session_factory() as db:
            owners = list(
                db.scalars(
                    select(FinancialTransaction.user_id).order_by(
                        FinancialTransaction.id
                    )
                )
            )
        self.assertEqual(owners, [self.other_user.id, self.user.id])

    def test_import_endpoints_require_authentication(self) -> None:
        preview = self.client.post(
            "/api/transactions/import/preview",
            json={"filename": "extrato.csv", "content": self._valid_csv()},
        )
        confirm = self.client.post(
            "/api/transactions/import/confirm",
            json={"rows": []},
        )
        self.assertEqual(preview.status_code, 401)
        self.assertEqual(confirm.status_code, 401)

    def _preview(
        self,
        content: str,
        *,
        token: str | None = None,
        mapping: dict | None = None,
    ):
        payload = {"filename": "extrato.csv", "content": content}
        if mapping is not None:
            payload["mapping"] = mapping
        return self.client.post(
            "/api/transactions/import/preview",
            json=payload,
            headers=self._headers(token or self.token),
        )

    def _confirm(
        self,
        token: str,
        row: dict,
        *,
        allow_duplicate: bool = False,
    ):
        return self.client.post(
            "/api/transactions/import/confirm",
            json={
                "rows": [
                    {
                        "date": row["date"],
                        "description": row["description"],
                        "amount": row["amount"],
                        "type": row["type"],
                        "category": row["category"],
                        "allow_duplicate": allow_duplicate,
                    }
                ]
            },
            headers=self._headers(token),
        )

    @staticmethod
    def _valid_csv() -> str:
        return "Data;Descrição;Valor;Tipo\n18/09/2026;IFOOD;40,00;Débito\n"

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _user(db, *, email: str, phone: str) -> User:
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
