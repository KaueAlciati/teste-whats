import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.base import Base
from backend.models import (  # noqa: F401
    Category,
    FinancialTransaction,
    PendingReceipt,
    User,
)
from backend.schemas.receipt_extraction import ReceiptExtraction
from backend.services.financial_assistant_service import handle_financial_message
from backend.services.receipt_assistant_service import (
    _process_receipt_extraction,
    handle_pending_receipt_reply,
)
from backend.services.user_service import get_or_create_whatsapp_user


class ReceiptProcessingTestCase(unittest.TestCase):
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
        self.session = self.session_factory()
        self._seed_categories()
        self.user = get_or_create_whatsapp_user(
            self.session,
            "5515999999999",
        )
        self.current_date = date(2026, 9, 18)
        self.current_time = datetime(
            2026,
            9,
            18,
            12,
            0,
            tzinfo=timezone(timedelta(hours=-3)),
        )

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_high_confidence_pix_outflow_creates_one_expense(self) -> None:
        response = self._process(
            "image-outflow",
            self._extraction(
                amount="85.00",
                direction="outflow",
                recipient_name="Mercado X",
                description="PIX para Mercado X",
                category_suggestion="Compras",
            ),
        )

        transaction = self._transaction("image-outflow")
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.type, "expense")
        self.assertEqual(transaction.amount, Decimal("85.00"))
        self.assertEqual(transaction.source, "whatsapp_image")
        self.assertIn("Mercado X", response)

    def test_high_confidence_pix_inflow_creates_one_income(self) -> None:
        response = self._process(
            "image-inflow",
            self._extraction(
                amount="250.00",
                direction="inflow",
                payer_name="João Silva",
                recipient_name=None,
                description="PIX recebido",
                category_suggestion="Outros",
            ),
        )

        transaction = self._transaction("image-inflow")
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.type, "income")
        self.assertEqual(transaction.amount, Decimal("250.00"))
        self.assertIn("João Silva", response)

    def test_clear_caption_resolves_unknown_direction(self) -> None:
        response = self._process(
            "image-caption-direction",
            self._extraction(
                direction="unknown",
                requires_confirmation=True,
            ),
            caption="paguei isso",
        )

        transaction = self._transaction("image-caption-direction")
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.type, "expense")
        self.assertIsNone(self._pending("image-caption-direction"))
        self.assertIn("salvo", response)

    def test_natural_received_caption_resolves_inflow(self) -> None:
        response = self._process(
            "image-caption-inflow",
            self._extraction(
                direction="unknown",
                requires_confirmation=True,
                payer_name="Cliente",
                recipient_name=None,
            ),
            caption="Recebi um pix, guarda pra mim",
        )

        transaction = self._transaction("image-caption-inflow")
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.type, "income")
        self.assertIsNone(self._pending("image-caption-inflow"))
        self.assertIn("recebimento", response)

    def test_caption_conflict_forces_confirmation(self) -> None:
        response = self._process(
            "image-caption-conflict",
            self._extraction(direction="inflow"),
            caption="paguei isso",
        )

        self.assertIsNone(self._transaction("image-caption-conflict"))
        self.assertIsNotNone(self._pending("image-caption-conflict"))
        self.assertIn("pagou", response)

    def test_unknown_direction_creates_pending_without_transaction(self) -> None:
        extraction = self._extraction(
            direction="unknown",
            requires_confirmation=True,
            pix_key="sensitive@example.com",
            end_to_end_id="E123456789",
        )

        response = self._process("image-unknown", extraction)

        self.assertIsNone(self._transaction("image-unknown"))
        pending = self._pending("image-unknown")
        self.assertIsNotNone(pending)
        self.assertNotIn("pix_key", pending.extracted_data)
        self.assertNotIn("end_to_end_id", pending.extracted_data)
        self.assertIn("pagou", response)
        self.assertIn("recebeu", response)

    def test_new_pending_replaces_older_pending_for_same_user(self) -> None:
        self._create_direction_pending("pending-old")
        self._create_direction_pending("pending-new")

        pending_ids = list(
            self.session.scalars(
                select(PendingReceipt.whatsapp_message_id).where(
                    PendingReceipt.user_id == self.user.id
                )
            )
        )
        self.assertEqual(pending_ids, ["pending-new"])

    def test_pending_reply_paid_creates_expense(self) -> None:
        self._create_direction_pending("pending-paid")

        result = handle_pending_receipt_reply(
            self.session,
            user=self.user,
            text="paguei",
            current_date=self.current_date,
            current_time=self.current_time + timedelta(minutes=1),
        )

        transaction = self._transaction("pending-paid")
        self.assertTrue(result.handled)
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.type, "expense")
        self.assertIsNone(self._pending("pending-paid"))

    def test_pending_reply_received_creates_income(self) -> None:
        self._create_direction_pending("pending-received")

        result = handle_pending_receipt_reply(
            self.session,
            user=self.user,
            text="recebi",
            current_date=self.current_date,
            current_time=self.current_time + timedelta(minutes=1),
        )

        transaction = self._transaction("pending-received")
        self.assertTrue(result.handled)
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.type, "income")

    def test_text_flow_resolves_pending_before_calling_groq(self) -> None:
        self._create_direction_pending("pending-text-flow")

        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message"
        ) as ai_mock:
            response = handle_financial_message(
                self.session,
                user=self.user,
                text="paguei",
                whatsapp_message_id="confirmation-text-message",
                current_date=self.current_date,
                current_datetime=self.current_time + timedelta(minutes=1),
            )

        ai_mock.assert_not_called()
        transaction = self._transaction("pending-text-flow")
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.type, "expense")
        self.assertIn("salvo", response)

    def test_expired_pending_does_not_register(self) -> None:
        self._create_direction_pending("pending-expired")
        pending = self._pending("pending-expired")
        pending.expires_at = self.current_time - timedelta(seconds=1)
        self.session.commit()

        result = handle_pending_receipt_reply(
            self.session,
            user=self.user,
            text="paguei",
            current_date=self.current_date,
            current_time=self.current_time,
        )

        self.assertTrue(result.handled)
        self.assertIn("expirou", result.response)
        self.assertIsNone(self._transaction("pending-expired"))
        self.assertIsNone(self._pending("pending-expired"))

    def test_unreadable_image_does_not_register(self) -> None:
        response = self._process(
            "image-unreadable",
            self._extraction(
                document_type="unknown",
                amount=None,
                currency=None,
                transaction_date=None,
                direction="unknown",
                status="unknown",
                confidence=0.20,
                requires_confirmation=True,
            ),
        )

        self.assertIsNone(self._transaction("image-unreadable"))
        self.assertIsNone(self._pending("image-unreadable"))
        self.assertIn("não parece ser um comprovante", response)

    def test_non_completed_statuses_do_not_register(self) -> None:
        for status in ("pending", "scheduled", "cancelled", "refunded"):
            with self.subTest(status=status):
                message_id = f"image-{status}"
                response = self._process(
                    message_id,
                    self._extraction(status=status),
                )
                self.assertIsNone(self._transaction(message_id))
                self.assertIsNone(self._pending(message_id))
                self.assertIn("não registrei", response.lower())

    def test_non_financial_image_does_not_register(self) -> None:
        self._process(
            "image-non-financial",
            self._extraction(
                document_type="unknown",
                direction="unknown",
                status="unknown",
                requires_confirmation=True,
            ),
        )

        self.assertIsNone(self._transaction("image-non-financial"))
        self.assertIsNone(self._pending("image-non-financial"))

    def test_invalid_amount_does_not_register(self) -> None:
        response = self._process(
            "image-invalid-amount",
            self._extraction(amount="saldo 1.250,00"),
        )

        self.assertIsNone(self._transaction("image-invalid-amount"))
        self.assertIsNone(self._pending("image-invalid-amount"))
        self.assertIn("Não consegui confirmar", response)

    def test_duplicate_image_message_id_creates_only_one_transaction(self) -> None:
        extraction = self._extraction()

        first_response = self._process("image-duplicate", extraction)
        second_response = self._process("image-duplicate", extraction)

        transaction_count = self.session.scalar(
            select(func.count(FinancialTransaction.id)).where(
                FinancialTransaction.whatsapp_message_id == "image-duplicate"
            )
        )
        self.assertIsNotNone(first_response)
        self.assertIsNone(second_response)
        self.assertEqual(transaction_count, 1)

    def test_other_user_cannot_confirm_pending_receipt(self) -> None:
        self._create_direction_pending("pending-user-a")
        other_user = get_or_create_whatsapp_user(
            self.session,
            "5515888888888",
        )

        result = handle_pending_receipt_reply(
            self.session,
            user=other_user,
            text="paguei",
            current_date=self.current_date,
            current_time=self.current_time + timedelta(minutes=1),
        )

        self.assertFalse(result.handled)
        self.assertIsNone(self._transaction("pending-user-a"))
        self.assertIsNotNone(self._pending("pending-user-a"))

    def test_amount_correction_updates_pending_without_registering(self) -> None:
        self._create_direction_pending("pending-amount")

        result = handle_pending_receipt_reply(
            self.session,
            user=self.user,
            text="na verdade é 85",
            current_date=self.current_date,
            current_time=self.current_time + timedelta(minutes=1),
        )

        pending = self._pending("pending-amount")
        self.assertTrue(result.handled)
        self.assertEqual(pending.extracted_data["amount"], "85.00")
        self.assertIsNone(self._transaction("pending-amount"))

    def _create_direction_pending(self, message_id: str) -> None:
        self._process(
            message_id,
            self._extraction(
                direction="unknown",
                requires_confirmation=True,
            ),
        )

    def _process(
        self,
        message_id: str,
        extraction: ReceiptExtraction,
        caption: str | None = None,
    ) -> str | None:
        with (
            patch(
                "backend.services.receipt_assistant_service.engine",
                self.engine,
            ),
            patch(
                "backend.services.receipt_assistant_service.SessionLocal",
                self.session_factory,
            ),
        ):
            response = _process_receipt_extraction(
                self.user.whatsapp_phone,
                message_id,
                extraction,
                self.current_time,
                caption,
            )
        self.session.expire_all()
        return response

    def _transaction(self, message_id: str) -> FinancialTransaction | None:
        self.session.expire_all()
        return self.session.scalar(
            select(FinancialTransaction).where(
                FinancialTransaction.whatsapp_message_id == message_id
            )
        )

    def _pending(self, message_id: str) -> PendingReceipt | None:
        self.session.expire_all()
        return self.session.scalar(
            select(PendingReceipt).where(
                PendingReceipt.whatsapp_message_id == message_id
            )
        )

    def _seed_categories(self) -> None:
        categories = {
            "expense": ("Compras", "Outros"),
            "income": ("Venda", "Outros"),
        }
        for transaction_type, names in categories.items():
            self.session.add_all(
                Category(
                    name=name,
                    type=transaction_type,
                    user_id=None,
                    is_default=True,
                )
                for name in names
            )
        self.session.commit()

    @staticmethod
    def _extraction(**overrides: object) -> ReceiptExtraction:
        values: dict[str, object] = {
            "document_type": "pix_receipt",
            "amount": "85.00",
            "currency": "BRL",
            "transaction_date": "2026-09-18",
            "transaction_time": "10:30:00",
            "payer_name": "Kaue",
            "payer_institution": "Banco A",
            "recipient_name": "Mercado X",
            "recipient_institution": "Banco B",
            "pix_key": None,
            "end_to_end_id": None,
            "description": "PIX",
            "direction": "outflow",
            "category_suggestion": "Outros",
            "status": "completed",
            "confidence": 0.98,
            "requires_confirmation": False,
            "reason": None,
        }
        values.update(overrides)
        return ReceiptExtraction(**values)


if __name__ == "__main__":
    unittest.main()
