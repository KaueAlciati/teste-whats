import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.api.webhook as webhook
from backend.main import app
from backend.services.ai_financial_service import FinancialAIServiceError
from backend.services.financial_assistant_service import AI_ERROR_MESSAGE


class WebhookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        webhook.VERIFY_TOKEN = "local-test-token"
        self.client = TestClient(app)

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


if __name__ == "__main__":
    unittest.main()
