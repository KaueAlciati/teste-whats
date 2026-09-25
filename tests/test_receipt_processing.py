import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database.base import Base
from backend.models import (  # noqa: F401
    Category,
    FinancialTransaction,
    PendingReceipt,
    TransactionAttachment,
    User,
)
from backend.schemas.receipt_extraction import ReceiptExtraction
from backend.services.attachment_service import (
    stage_attachment_file,
    validate_attachment,
)
from backend.services.financial_assistant_service import handle_financial_message
from backend.services.receipt_assistant_service import (
    _process_receipt_extraction,
    handle_pending_receipt_reply,
)
from backend.services.user_service import get_or_create_whatsapp_user


class ReceiptProcessingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ,
            {"ATTACHMENT_STORAGE_DIR": self.storage.name},
            clear=False,
        )
        self.environment.start()
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
        self.user = get_or_create_whatsapp_user(
            self.session,
            "5515999999999",
        )
        self.user.name = "Kaue"
        self.user.email = "kaue@example.com"
        self.user.password_hash = "argon2-test-hash"
        self.user.active = True
        self.session.commit()
        self.session.add_all(
            [
                Category(
                    name="Trabalho",
                    type="expense",
                    is_default=True,
                ),
                Category(
                    name="Transporte",
                    type="expense",
                    is_default=True,
                ),
            ]
        )
        self.session.commit()
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
        self.environment.stop()
        self.storage.cleanup()

    def test_image_requires_confirmation_then_creates_expense_and_attachment(
        self,
    ) -> None:
        response = self._process(
            "image-outflow",
            self._extraction(
                amount="85.00",
                direction="outflow",
                description="PIX para Mercado X",
            ),
        )

        self.assertIsNone(self._transaction("image-outflow"))
        self.assertIsNotNone(self._pending("image-outflow"))
        self.assertIn("85", response)
        self.assertIn("Sem categoria", response)

        result = self._reply("sim")
        transaction = self._transaction("image-outflow")
        attachment = self._attachment(transaction.id)
        self.assertTrue(result.handled)
        self.assertEqual(transaction.type, "expense")
        self.assertEqual(transaction.amount, Decimal("85.00"))
        self.assertEqual(transaction.source, "whatsapp_image")
        self.assertIsNone(transaction.category_id)
        self.assertEqual(attachment.mime_type, "image/png")
        self.assertTrue(self._stored_path(attachment.storage_key).is_file())
        self.assertIsNone(self._pending("image-outflow"))

    def test_pdf_requires_confirmation_then_creates_income_and_attachment(
        self,
    ) -> None:
        response = self._process(
            "document-inflow",
            self._extraction(
                amount="250.00",
                direction="inflow",
                description="PIX recebido",
            ),
            source="whatsapp_document",
        )

        self.assertIn("Entrada", response)
        result = self._reply("isso")
        transaction = self._transaction("document-inflow")
        attachment = self._attachment(transaction.id)
        self.assertTrue(result.handled)
        self.assertEqual(transaction.type, "income")
        self.assertEqual(transaction.source, "whatsapp_document")
        self.assertEqual(attachment.mime_type, "application/pdf")
        self.assertEqual(attachment.original_filename, "comprovante.pdf")

    def test_unknown_direction_waits_for_explicit_direction(self) -> None:
        response = self._process(
            "image-unknown",
            self._extraction(direction="unknown"),
        )

        self.assertIn("paguei", response)
        first_reply = self._reply("sim")
        self.assertIn("pagou", first_reply.response)
        self.assertIsNone(self._transaction("image-unknown"))

        second_reply = self._reply("paguei")
        self.assertTrue(second_reply.handled)
        self.assertEqual(self._transaction("image-unknown").type, "expense")

    def test_caption_sets_direction_but_still_requires_confirmation(self) -> None:
        response = self._process(
            "image-caption",
            self._extraction(direction="unknown"),
            caption="recebi um pix",
        )

        self.assertIn("Entrada", response)
        self.assertIsNone(self._transaction("image-caption"))
        self._reply("sim")
        self.assertEqual(self._transaction("image-caption").type, "income")

    def test_discard_removes_pending_and_staged_file(self) -> None:
        self._process("image-discard", self._extraction())
        pending = self._pending("image-discard")
        storage_key = pending.extracted_data["_attachment"]["storage_key"]
        self.assertTrue(self._stored_path(storage_key).is_file())

        result = self._reply("não")

        self.assertTrue(result.handled)
        self.assertIsNone(self._pending("image-discard"))
        self.assertFalse(self._stored_path(storage_key).exists())

    def test_duplicate_message_creates_only_one_transaction(self) -> None:
        extraction = self._extraction()
        self._process("image-duplicate", extraction)
        duplicate_response = self._process("image-duplicate", extraction)
        self._reply("sim")

        transaction_count = self.session.scalar(
            select(func.count(FinancialTransaction.id)).where(
                FinancialTransaction.whatsapp_message_id == "image-duplicate"
            )
        )
        attachment_count = self.session.scalar(
            select(func.count(TransactionAttachment.id))
        )
        self.assertIsNone(duplicate_response)
        self.assertEqual(transaction_count, 1)
        self.assertEqual(attachment_count, 1)

    def test_invalid_extraction_does_not_create_pending_or_transaction(self) -> None:
        response = self._process(
            "image-invalid",
            self._extraction(amount=None, confidence=0.2),
        )

        self.assertIsNone(self._pending("image-invalid"))
        self.assertIsNone(self._transaction("image-invalid"))
        self.assertIn("Não consegui", response)

    def test_expired_pending_is_discarded_without_transaction(self) -> None:
        self._process("image-expired", self._extraction())
        pending = self._pending("image-expired")
        pending.expires_at = self.current_time - timedelta(seconds=1)
        self.session.commit()

        result = self._reply("sim")

        self.assertTrue(result.handled)
        self.assertIn("expirou", result.response)
        self.assertIsNone(self._transaction("image-expired"))
        self.assertIsNone(self._pending("image-expired"))

    def test_other_user_cannot_confirm_pending(self) -> None:
        self._process("image-user-a", self._extraction())
        other_user = get_or_create_whatsapp_user(
            self.session,
            "5515888888888",
        )
        other_user.email = "other@example.com"
        other_user.password_hash = "argon2-other-hash"
        self.session.commit()

        result = handle_pending_receipt_reply(
            self.session,
            user=other_user,
            text="sim",
            current_date=self.current_date,
            current_time=self.current_time + timedelta(minutes=1),
        )

        self.assertFalse(result.handled)
        self.assertIsNone(self._transaction("image-user-a"))
        self.assertIsNotNone(self._pending("image-user-a"))

    def test_text_confirmation_is_resolved_before_financial_ai(self) -> None:
        self._process("image-text-confirm", self._extraction())

        with patch(
            "backend.services.financial_assistant_service.interpret_financial_message"
        ) as ai_mock:
            response = handle_financial_message(
                self.session,
                user=self.user,
                text="isso mesmo",
                whatsapp_message_id="confirmation-text-message",
                current_date=self.current_date,
                current_datetime=self.current_time + timedelta(minutes=1),
            )

        ai_mock.assert_not_called()
        self.assertIsNotNone(self._transaction("image-text-confirm"))
        self.assertIn("salvo", response)

    def test_amount_correction_keeps_same_pending_context(self) -> None:
        self._process("image-correction", self._extraction())

        result = self._reply("na verdade é 90")
        pending = self._pending("image-correction")

        self.assertTrue(result.handled)
        self.assertEqual(pending.extracted_data["amount"], "90.00")
        self.assertIsNone(self._transaction("image-correction"))

    def test_pending_receipt_accepts_natural_field_corrections(self) -> None:
        cases = (
            ("categoria trabalho", "category_suggestion", "Trabalho", "Trabalho"),
            (
                "Categoria trabalho o comprovante arrume pra mim",
                "category_suggestion",
                "Trabalho",
                "Trabalho",
            ),
            (
                "muda a categoria para Transporte",
                "category_suggestion",
                "Transporte",
                "Transporte",
            ),
            ("o valor era 180", "amount", "180.00", "R$ 180,00"),
            (
                "a descrição é manutenção",
                "description",
                "manutenção",
                "Manutenção",
            ),
            (
                "foi ontem",
                "transaction_date",
                "2026-09-17",
                "17/09/2026",
            ),
            ("isso é uma entrada", "direction", "inflow", "Entrada"),
        )
        for index, (reply, field, expected_value, expected_response) in enumerate(cases):
            with self.subTest(reply=reply):
                message_id = f"receipt-field-correction-{index}"
                self._process(message_id, self._extraction(amount="175.00"))

                result = self._reply(reply)
                pending = self._pending(message_id)

                self.assertTrue(result.handled)
                self.assertEqual(pending.extracted_data[field], expected_value)
                self.assertIn("Comprovante atualizado", result.response)
                self.assertIn(expected_response, result.response)
                self.assertNotIn("Qual o valor", result.response)
                self.assertIsNone(self._transaction(message_id))

    def test_unknown_receipt_category_is_not_invented(self) -> None:
        self._process("receipt-invalid-category", self._extraction())

        result = self._reply("categoria teletransporte")
        pending = self._pending("receipt-invalid-category")

        self.assertTrue(result.handled)
        self.assertIn("Não encontrei essa categoria", result.response)
        self.assertIsNone(pending.extracted_data["category_suggestion"])
        self.assertIsNone(self._transaction("receipt-invalid-category"))

    def _reply(self, text: str):
        return handle_pending_receipt_reply(
            self.session,
            user=self.user,
            text=text,
            current_date=self.current_date,
            current_time=self.current_time + timedelta(minutes=1),
        )

    def _process(
        self,
        message_id: str,
        extraction: ReceiptExtraction,
        caption: str | None = None,
        *,
        source: str = "whatsapp_image",
    ) -> str | None:
        if source == "whatsapp_document":
            content = b"%PDF-1.4\nreceipt"
            filename = "comprovante.pdf"
            mime_type = "application/pdf"
        else:
            content = b"\x89PNG\r\n\x1a\nreceipt"
            filename = "comprovante.png"
            mime_type = "image/png"
        attachment = stage_attachment_file(
            validate_attachment(
                content,
                filename=filename,
                mime_type=mime_type,
            ),
            user_id=self.user.id,
        )
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
                attachment,
                source,
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

    def _attachment(self, transaction_id: int) -> TransactionAttachment:
        self.session.expire_all()
        return self.session.scalar(
            select(TransactionAttachment).where(
                TransactionAttachment.transaction_id == transaction_id
            )
        )

    def _stored_path(self, storage_key: str) -> Path:
        return Path(self.storage.name) / storage_key

    @staticmethod
    def _extraction(**overrides: object) -> ReceiptExtraction:
        values: dict[str, object] = {
            "document_type": "payment_receipt",
            "amount": "85.00",
            "currency": "BRL",
            "transaction_date": "2026-09-18",
            "transaction_time": None,
            "payer_name": None,
            "payer_institution": None,
            "recipient_name": None,
            "recipient_institution": None,
            "pix_key": None,
            "end_to_end_id": None,
            "description": "PIX Mercado X",
            "direction": "outflow",
            "category_suggestion": None,
            "status": "completed",
            "confidence": 0.98,
            "requires_confirmation": True,
            "reason": None,
        }
        values.update(overrides)
        return ReceiptExtraction(**values)


if __name__ == "__main__":
    unittest.main()
