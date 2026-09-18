import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.schemas.receipt_extraction import ReceiptExtraction
from backend.services.receipt_assistant_service import (
    process_financial_image_message,
)
from backend.services.whatsapp_media_service import WhatsAppMedia


class ImageProcessingTestCase(unittest.TestCase):
    def test_image_flow_sends_intermediate_and_final_messages(self) -> None:
        media = WhatsAppMedia(
            content=b"\x89PNG\r\n\x1a\nimage",
            mime_type="image/png",
            filename="image.png",
        )
        extraction = ReceiptExtraction(
            document_type="pix_receipt",
            amount="85.00",
            currency="BRL",
            transaction_date="2026-09-18",
            transaction_time=None,
            payer_name=None,
            payer_institution=None,
            recipient_name="Mercado X",
            recipient_institution=None,
            pix_key=None,
            end_to_end_id=None,
            description="PIX para Mercado X",
            direction="outflow",
            category_suggestion="Compras",
            status="completed",
            confidence=0.98,
            requires_confirmation=False,
            reason=None,
        )
        send_mock = AsyncMock(return_value=True)
        download_mock = AsyncMock(return_value=media)
        analyze_mock = Mock(return_value=extraction)

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
                "backend.services.receipt_assistant_service._get_user_name",
                return_value="Kaue",
            ),
            patch(
                "backend.services.receipt_assistant_service.analyze_receipt_image",
                analyze_mock,
            ),
            patch(
                "backend.services.receipt_assistant_service._process_receipt_extraction",
                return_value="comprovante registrado",
            ) as process_mock,
            patch(
                "backend.services.receipt_assistant_service.send_text_message",
                send_mock,
            ),
        ):
            asyncio.run(
                process_financial_image_message(
                    "5515999999999",
                    "wamid.image",
                    "media-id",
                    "image/png",
                    "paguei isso",
                )
            )

        self.assertEqual(send_mock.await_count, 2)
        self.assertIn("comprovante", send_mock.await_args_list[0].args[1])
        self.assertEqual(
            send_mock.await_args_list[1].args,
            ("5515999999999", "comprovante registrado"),
        )
        download_mock.assert_awaited_once_with(
            "media-id",
            fallback_mime_type="image/png",
            media_kind="image",
        )
        self.assertEqual(
            analyze_mock.call_args.kwargs["caption"],
            "paguei isso",
        )
        process_mock.assert_called_once()

    def test_duplicate_image_is_not_downloaded_again(self) -> None:
        download_mock = AsyncMock()
        send_mock = AsyncMock()

        with (
            patch(
                "backend.services.receipt_assistant_service._image_message_already_handled",
                return_value=True,
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


if __name__ == "__main__":
    unittest.main()
