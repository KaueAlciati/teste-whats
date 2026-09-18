import base64
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
        client.responses.parse.return_value = SimpleNamespace(
            output_parsed=extraction
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
        call = client.responses.parse.call_args
        self.assertEqual(call.kwargs["model"], DEFAULT_VISION_MODEL)
        self.assertIs(call.kwargs["text_format"], ReceiptExtraction)
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
