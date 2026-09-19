import base64
import json
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx2
from openai import APIStatusError, APITimeoutError
from openai.lib._pydantic import to_strict_json_schema

from backend.schemas.receipt_extraction import ReceiptExtraction
from backend.services.image_understanding_service import (
    DEFAULT_VISION_MODEL,
    GROQ_BASE_URL,
    ImageUnderstandingError,
    analyze_receipt_image,
)


class ImageUnderstandingServiceTestCase(unittest.TestCase):
    def test_sends_base64_image_caption_and_structured_schema(self) -> None:
        extraction = self._extraction()
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(extraction.model_dump(mode="json"))
        )
        image_bytes = b"safe-image-bytes"

        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": "test-key"},
            clear=True,
        ):
            with patch(
                "backend.services.image_understanding_service.OpenAI",
                return_value=client,
            ) as openai_mock:
                result = analyze_receipt_image(
                    image_bytes,
                    mime_type="image/png",
                    current_date=date(2026, 9, 18),
                    caption="paguei isso",
                    user_name="Kaue",
                )

        self.assertEqual(result, extraction)
        self.assertEqual(
            openai_mock.call_args.kwargs["base_url"],
            GROQ_BASE_URL,
        )
        call = client.responses.create.call_args
        self.assertEqual(call.kwargs["model"], DEFAULT_VISION_MODEL)
        self.assertEqual(
            call.kwargs["text"],
            {"format": {"type": "json_object"}},
        )
        content = call.kwargs["input"][0]["content"]
        self.assertIn("paguei isso", content[0]["text"])
        expected_data = base64.b64encode(image_bytes).decode("ascii")
        self.assertEqual(
            content[1]["image_url"],
            f"data:image/png;base64,{expected_data}",
        )

    def test_receipt_schema_is_compatible_with_strict_output(self) -> None:
        schema = to_strict_json_schema(ReceiptExtraction)

        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            set(schema["properties"]),
        )

    def test_missing_key_fails_without_exposing_secret(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ImageUnderstandingError):
                analyze_receipt_image(
                    b"image",
                    mime_type="image/jpeg",
                    current_date=date(2026, 9, 18),
                )

    def test_provider_http_errors_are_wrapped_and_logged_safely(self) -> None:
        for status_code in (400, 401, 429, 500):
            with self.subTest(status_code=status_code):
                request = httpx2.Request(
                    "POST",
                    f"{GROQ_BASE_URL}/responses",
                )
                response = httpx2.Response(status_code, request=request)
                error = APIStatusError(
                    "provider rejected request",
                    response=response,
                    body={"error": "safe test error"},
                )
                client = Mock()
                client.responses.create.side_effect = error

                with patch.dict(
                    os.environ,
                    {"GROQ_API_KEY": "test-secret-key"},
                    clear=True,
                ):
                    with (
                        patch(
                            "backend.services.image_understanding_service.OpenAI",
                            return_value=client,
                        ),
                        patch(
                            "backend.services.image_understanding_service.logger"
                        ) as logger,
                    ):
                        with self.assertRaises(ImageUnderstandingError):
                            analyze_receipt_image(
                                b"image",
                                mime_type="image/jpeg",
                                current_date=date(2026, 9, 18),
                            )

                self.assertIn(str(status_code), str(logger.error.mock_calls))
                self.assertNotIn("test-secret-key", str(logger.mock_calls))

    def test_timeout_is_wrapped(self) -> None:
        request = httpx2.Request("POST", f"{GROQ_BASE_URL}/responses")
        client = Mock()
        client.responses.create.side_effect = APITimeoutError(request=request)

        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": "test-key"},
            clear=True,
        ):
            with patch(
                "backend.services.image_understanding_service.OpenAI",
                return_value=client,
            ):
                with self.assertRaises(ImageUnderstandingError):
                    analyze_receipt_image(
                        b"image",
                        mime_type="image/jpeg",
                        current_date=date(2026, 9, 18),
                    )

    def test_invalid_json_is_rejected(self) -> None:
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text="not-json"
        )

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True):
            with patch(
                "backend.services.image_understanding_service.OpenAI",
                return_value=client,
            ):
                with self.assertRaises(ImageUnderstandingError):
                    analyze_receipt_image(
                        b"image",
                        mime_type="image/png",
                        current_date=date(2026, 9, 18),
                    )

    def test_pydantic_validation_error_is_rejected(self) -> None:
        invalid_payload = self._extraction().model_dump(mode="json")
        invalid_payload["direction"] = "sideways"
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=json.dumps(invalid_payload)
        )

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True):
            with patch(
                "backend.services.image_understanding_service.OpenAI",
                return_value=client,
            ):
                with self.assertRaises(ImageUnderstandingError):
                    analyze_receipt_image(
                        b"image",
                        mime_type="image/webp",
                        current_date=date(2026, 9, 18),
                    )

    @staticmethod
    def _extraction() -> ReceiptExtraction:
        return ReceiptExtraction(
            document_type="pix_receipt",
            amount="85.00",
            currency="BRL",
            transaction_date="2026-09-18",
            transaction_time="10:30:00",
            payer_name="Kaue",
            payer_institution="Banco A",
            recipient_name="Mercado X",
            recipient_institution="Banco B",
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


if __name__ == "__main__":
    unittest.main()
