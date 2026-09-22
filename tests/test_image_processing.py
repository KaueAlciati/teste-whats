import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.schemas.statement_import import (
    StatementDocumentExtraction,
    StatementExtractedMovement,
)
from backend.services.attachment_service import StoredAttachment
from backend.services.receipt_assistant_service import (
    process_financial_document_message,
    process_financial_image_message,
)
from backend.services.whatsapp_media_service import WhatsAppMedia


class ImageProcessingTestCase(unittest.TestCase):
    def test_image_uses_shared_web_parser_and_creates_confirmation(self) -> None:
        media = WhatsAppMedia(
            content=b"\x89PNG\r\n\x1a\nimage",
            mime_type="image/png",
            filename="image.png",
        )
        self._assert_media_flow(
            media=media,
            runner=lambda: process_financial_image_message(
                "5515999999999",
                "wamid.image",
                "media-id",
                "image/png",
                "paguei isso",
            ),
            media_kind="image",
            source="whatsapp_image",
            fallback_filename=None,
        )

    def test_pdf_uses_shared_web_parser_and_creates_confirmation(self) -> None:
        media = WhatsAppMedia(
            content=b"%PDF-1.4\nreceipt",
            mime_type="application/pdf",
            filename="comprovante.pdf",
        )
        self._assert_media_flow(
            media=media,
            runner=lambda: process_financial_document_message(
                "5515999999999",
                "wamid.pdf",
                "media-id",
                "application/pdf",
                "comprovante.pdf",
                None,
            ),
            media_kind="document",
            source="whatsapp_document",
            fallback_filename="comprovante.pdf",
        )

    def test_duplicate_image_is_not_downloaded_again(self) -> None:
        download_mock = AsyncMock()
        send_mock = AsyncMock()

        with (
            patch(
                "backend.services.receipt_assistant_service._image_message_already_handled",
                return_value=True,
            ),
            patch(
                "backend.services.receipt_assistant_service._get_authorized_user_id",
                return_value=1,
            ),
            patch(
                "backend.services.receipt_assistant_service.download_whatsapp_media",
                download_mock,
            ),
            patch(
                "backend.services.receipt_assistant_service.send_text_message",
                send_mock,
            ),
        ):
            asyncio.run(
                process_financial_image_message(
                    "5515999999999",
                    "wamid.duplicate-image",
                    "media-id",
                    "image/jpeg",
                    None,
                )
            )

        download_mock.assert_not_awaited()
        send_mock.assert_not_awaited()

    def _assert_media_flow(
        self,
        *,
        media: WhatsAppMedia,
        runner,
        media_kind: str,
        source: str,
        fallback_filename: str | None,
    ) -> None:
        extraction = StatementDocumentExtraction(
            document_type="single_receipt",
            movements=[
                StatementExtractedMovement(
                    transaction_date="2026-09-18",
                    description="PIX para Mercado X",
                    amount="85.00",
                    direction="outflow",
                    confidence=0.98,
                    reason=None,
                )
            ],
            reason=None,
        )
        staged = StoredAttachment(
            storage_key="pending/users/1/aa/file.png",
            original_filename=media.filename,
            mime_type=media.mime_type,
            size_bytes=len(media.content),
            sha256="a" * 64,
        )
        send_mock = AsyncMock(return_value=True)
        download_mock = AsyncMock(return_value=media)
        parser_mock = Mock(return_value=extraction)
        process_mock = Mock(return_value="Confirme os dados do comprovante")

        with (
            patch(
                "backend.services.receipt_assistant_service._image_message_already_handled",
                return_value=False,
            ),
            patch(
                "backend.services.receipt_assistant_service.download_whatsapp_media",
                download_mock,
            ),
            patch(
                "backend.services.receipt_assistant_service.extract_statement_document",
                parser_mock,
            ),
            patch(
                "backend.services.receipt_assistant_service._get_authorized_user_id",
                return_value=1,
            ),
            patch(
                "backend.services.receipt_assistant_service.stage_attachment_file",
                return_value=staged,
            ),
            patch(
                "backend.services.receipt_assistant_service._process_receipt_extraction",
                process_mock,
            ),
            patch(
                "backend.services.receipt_assistant_service.send_text_message",
                send_mock,
            ),
        ):
            asyncio.run(runner())

        self.assertEqual(send_mock.await_count, 2)
        self.assertIn("comprovante", send_mock.await_args_list[0].args[1])
        self.assertEqual(
            send_mock.await_args_list[1].args,
            ("5515999999999", "Confirme os dados do comprovante"),
        )
        download_mock.assert_awaited_once_with(
            "media-id",
            fallback_mime_type=media.mime_type,
            fallback_filename=fallback_filename,
            media_kind=media_kind,
        )
        parser_mock.assert_called_once_with(
            media.content,
            mime_type=media.mime_type,
            filename=media.filename,
        )
        self.assertEqual(process_mock.call_args.args[-1], source)


if __name__ == "__main__":
    unittest.main()
