import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.api.webhook as webhook
from backend.main import app
from backend.services.ai_financial_service import FinancialAIServiceError
from backend.services.audio_transcription_service import AudioTranscriptionError
from backend.services.conversation_service import audio_error_response
from backend.services.financial_assistant_service import AI_ERROR_MESSAGE
from backend.services.whatsapp_media_service import (
    WhatsAppMedia,
    WhatsAppMediaError,
)


class WebhookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        webhook.VERIFY_TOKEN = "local-test-token"
        self.access_patcher = patch.object(
            webhook,
            "authorize_registered_whatsapp_phone",
            return_value=True,
        )
        self.access_patcher.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.access_patcher.stop()

    def test_get_webhook_remains_compatible(self) -> None:
        response = self.client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "local-test-token",
                "hub.challenge": "12345",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "12345")

    def test_text_message_schedules_financial_assistant(self) -> None:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "5511000000000"},
                        "messages": [{
                            "from": "5515999999999",
                            "id": "wamid.test-message",
                            "type": "text",
                            "text": {"body": "gastei 40 reais de gasolina"},
                        }],
                    }
                }]
            }]
        }
        process_mock = AsyncMock(return_value=None)

        with patch.object(
            webhook,
            "process_financial_message",
            process_mock,
        ):
            response = self.client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        process_mock.assert_awaited_once_with(
            "5515999999999",
            "wamid.test-message",
            "gastei 40 reais de gasolina",
        )

    def test_audio_message_schedules_financial_assistant(self) -> None:
        payload = self._audio_payload("wamid.audio-message")
        process_mock = AsyncMock(return_value=None)

        with patch.object(
            webhook,
            "process_financial_audio_message",
            process_mock,
        ):
            response = self.client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        process_mock.assert_awaited_once_with(
            "5515999999999",
            "wamid.audio-message",
            "media-id",
            "audio/ogg; codecs=opus",
        )

    def test_image_message_schedules_receipt_assistant_with_caption(self) -> None:
        payload = self._image_payload("wamid.image-message")
        process_mock = AsyncMock(return_value=None)

        with patch.object(
            webhook,
            "process_financial_image_message",
            process_mock,
        ):
            response = self.client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        process_mock.assert_awaited_once_with(
            "5515999999999",
            "wamid.image-message",
            "image-media-id",
            "image/jpeg",
            "paguei isso",
        )

    def test_pdf_document_schedules_same_receipt_flow(self) -> None:
        payload = self._document_payload("wamid.document-message")
        process_mock = AsyncMock(return_value=None)

        with patch.object(
            webhook,
            "process_financial_document_message",
            process_mock,
        ):
            response = self.client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        process_mock.assert_awaited_once_with(
            "5515999999999",
            "wamid.document-message",
            "document-media-id",
            "application/pdf",
            "comprovante.pdf",
            "comprovante",
        )

    def test_unauthorized_image_is_not_processed(self) -> None:
        process_mock = AsyncMock(return_value=None)
        with (
            patch.object(
                webhook,
                "authorize_registered_whatsapp_phone",
                return_value=False,
            ),
            patch.object(
                webhook,
                "process_financial_image_message",
                process_mock,
            ),
        ):
            response = self.client.post(
                "/webhook",
                json=self._image_payload("wamid.unauthorized-image"),
            )

        self.assertEqual(response.status_code, 200)
        process_mock.assert_not_awaited()

    def test_audio_download_error_does_not_break_webhook(self) -> None:
        send_mock = AsyncMock(return_value=True)

        with (
            patch(
                "backend.services.financial_assistant_service._message_already_processed",
                return_value=False,
            ),
            patch(
                "backend.services.financial_assistant_service.download_whatsapp_media",
                AsyncMock(side_effect=WhatsAppMediaError("download failed")),
            ),
            patch(
                "backend.services.financial_assistant_service.send_text_message",
                send_mock,
            ),
        ):
            response = self.client.post(
                "/webhook",
                json=self._audio_payload("wamid.download-error"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(
            send_mock.await_args_list[-1].args,
            ("5515999999999", audio_error_response()),
        )

    def test_audio_transcription_error_does_not_break_webhook(self) -> None:
        send_mock = AsyncMock(return_value=True)
        media = WhatsAppMedia(
            content=b"audio-bytes",
            mime_type="audio/ogg",
            filename="audio.ogg",
        )

        with (
            patch(
                "backend.services.financial_assistant_service._message_already_processed",
                return_value=False,
            ),
            patch(
                "backend.services.financial_assistant_service.download_whatsapp_media",
                AsyncMock(return_value=media),
            ),
            patch(
                "backend.services.financial_assistant_service.transcribe_audio",
                AsyncMock(
                    side_effect=AudioTranscriptionError("transcription failed")
                ),
            ),
            patch(
                "backend.services.financial_assistant_service.send_text_message",
                send_mock,
            ),
        ):
            response = self.client.post(
                "/webhook",
                json=self._audio_payload("wamid.transcription-error"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(
            send_mock.await_args_list[-1].args,
            ("5515999999999", audio_error_response()),
        )

    def test_meta_status_event_is_ignored(self) -> None:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{"status": "delivered"}],
                    }
                }]
            }]
        }
        process_mock = AsyncMock(return_value=None)

        with patch.object(
            webhook,
            "process_financial_message",
            process_mock,
        ):
            response = self.client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        process_mock.assert_not_awaited()

    def test_openai_error_does_not_break_webhook(self) -> None:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "5515999999999",
                            "id": "wamid.ai-error",
                            "type": "text",
                            "text": {"body": "gastei 40"},
                        }],
                    }
                }]
            }]
        }
        send_mock = AsyncMock(return_value=True)

        with patch(
            "backend.services.financial_assistant_service._process_financial_message",
            side_effect=FinancialAIServiceError("internal error"),
        ):
            with patch(
                "backend.services.financial_assistant_service.send_text_message",
                send_mock,
            ):
                response = self.client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        send_mock.assert_awaited_once_with("5515999999999", AI_ERROR_MESSAGE)

    def test_message_without_id_is_ignored_for_idempotency(self) -> None:
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "5515999999999",
                            "type": "text",
                            "text": {"body": "gastei 40"},
                        }],
                    }
                }]
            }]
        }
        process_mock = AsyncMock(return_value=None)

        with patch.object(
            webhook,
            "process_financial_message",
            process_mock,
        ):
            response = self.client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        process_mock.assert_not_awaited()

    @staticmethod
    def _audio_payload(message_id: str) -> dict[str, object]:
        return {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "5511000000000"},
                        "messages": [{
                            "from": "5515999999999",
                            "id": message_id,
                            "type": "audio",
                            "audio": {
                                "id": "media-id",
                                "mime_type": "audio/ogg; codecs=opus",
                            },
                        }],
                    }
                }]
            }]
        }

    @staticmethod
    def _image_payload(message_id: str) -> dict[str, object]:
        return {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "5511000000000"},
                        "messages": [{
                            "from": "5515999999999",
                            "id": message_id,
                            "type": "image",
                            "image": {
                                "id": "image-media-id",
                                "mime_type": "image/jpeg",
                                "caption": "paguei isso",
                            },
                        }],
                    }
                }]
            }]
        }

    @staticmethod
    def _document_payload(message_id: str) -> dict[str, object]:
        return {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {"display_phone_number": "5511000000000"},
                        "messages": [{
                            "from": "5515999999999",
                            "id": message_id,
                            "type": "document",
                            "document": {
                                "id": "document-media-id",
                                "mime_type": "application/pdf",
                                "filename": "comprovante.pdf",
                                "caption": "comprovante",
                            },
                        }],
                    }
                }]
            }]
        }


if __name__ == "__main__":
    unittest.main()
