import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pymupdf

from backend.schemas.statement_import import (
    StatementDocumentExtraction,
    StatementExtractedMovement,
)
from backend.services.statement_document_service import (
    StatementDocumentError,
    _analyze_statement_content,
    _extract_pdf_text_chunks,
    _merge_extractions,
    _render_pdf_pages,
    extract_statement_document,
)


class StatementDocumentServiceTestCase(unittest.TestCase):
    def test_image_uses_vision_json_and_extracts_multiple_movements(self) -> None:
        extraction = self._extraction("Compra mercado", "Salário")
        client = Mock()
        client.chat.completions.create.return_value = self._completion(extraction)

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True):
            with patch(
                "backend.services.statement_document_service.OpenAI",
                return_value=client,
            ):
                result = extract_statement_document(
                    b"safe-image",
                    mime_type="image/jpeg",
                    filename="extrato.jpg",
                )

        self.assertEqual(result, extraction)
        call = client.chat.completions.create.call_args.kwargs
        self.assertEqual(call["response_format"], {"type": "json_object"})
        self.assertEqual(call["temperature"], 0)
        content = call["messages"][0]["content"]
        self.assertEqual(content[1]["type"], "image_url")
        self.assertIn("data:image/jpeg;base64,", content[1]["image_url"]["url"])
        self.assertIn("comprovante individual", content[0]["text"].casefold())

    def test_pdf_with_text_prioritizes_text_and_does_not_render(self) -> None:
        extraction = self._extraction("Mercado")
        with (
            patch(
                "backend.services.statement_document_service._extract_pdf_text_chunks",
                return_value=["20/09/2026 Mercado -40,00"],
            ),
            patch(
                "backend.services.statement_document_service._analyze_statement_content",
                return_value=extraction,
            ) as analyze,
            patch(
                "backend.services.statement_document_service._render_pdf_pages"
            ) as render,
        ):
            result = extract_statement_document(
                b"%PDF-safe",
                mime_type="application/pdf",
                filename="extrato.pdf",
            )

        self.assertEqual(result.document_type, "bank_statement")
        analyze.assert_called_once_with(
            text="20/09/2026 Mercado -40,00",
            images=None,
        )
        render.assert_not_called()

    def test_real_pdf_text_layer_is_extracted(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text(
            (72, 72),
            "Extrato bancario 20/09/2026 Mercado 40,00 saida",
        )
        pdf_bytes = document.tobytes()
        document.close()

        chunks = _extract_pdf_text_chunks(pdf_bytes)

        self.assertEqual(len(chunks), 1)
        self.assertIn("20/09/2026", chunks[0])
        self.assertIn("Mercado", chunks[0])

    def test_real_scanned_pdf_page_is_rendered_as_jpeg(self) -> None:
        document = pymupdf.open()
        document.new_page()
        pdf_bytes = document.tobytes()
        document.close()

        pages = _render_pdf_pages(pdf_bytes)

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0][1], "image/jpeg")
        self.assertTrue(pages[0][0].startswith(b"\xff\xd8\xff"))

    def test_scanned_pdf_renders_pages_in_batches_of_three(self) -> None:
        first = self._extraction("Linha 1")
        second = self._extraction("Linha 2")
        rendered = [(f"page-{index}".encode(), "image/jpeg") for index in range(4)]
        with (
            patch(
                "backend.services.statement_document_service._extract_pdf_text_chunks",
                return_value=[],
            ),
            patch(
                "backend.services.statement_document_service._render_pdf_pages",
                return_value=rendered,
            ),
            patch(
                "backend.services.statement_document_service._analyze_statement_content",
                side_effect=[first, second],
            ) as analyze,
        ):
            result = extract_statement_document(
                b"%PDF-scanned",
                mime_type="application/pdf",
                filename="digitalizado.pdf",
            )

        self.assertEqual(len(result.movements), 2)
        self.assertEqual(analyze.call_count, 2)
        self.assertEqual(len(analyze.call_args_list[0].kwargs["images"]), 3)
        self.assertEqual(len(analyze.call_args_list[1].kwargs["images"]), 1)

    def test_single_receipt_classification_is_preserved(self) -> None:
        extraction = StatementDocumentExtraction(
            document_type="single_receipt",
            movements=[
                StatementExtractedMovement(
                    transaction_date="2026-09-22",
                    description="PIX enviado",
                    amount="42.00",
                    direction="outflow",
                    confidence=0.99,
                    reason=None,
                )
            ],
            reason="Comprovante PIX",
        )
        client = Mock()
        client.chat.completions.create.return_value = self._completion(extraction)
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True):
            with patch(
                "backend.services.statement_document_service.OpenAI",
                return_value=client,
            ):
                result = extract_statement_document(
                    b"safe-image",
                    mime_type="image/png",
                    filename="pix.png",
                )
        self.assertEqual(result.document_type, "single_receipt")
        self.assertEqual(len(result.movements), 1)
        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("exatamente uma movement", prompt[0]["text"])
        self.assertIn("use unknown", prompt[0]["text"])

    def test_merge_keeps_single_receipt_with_its_movement(self) -> None:
        extraction = StatementDocumentExtraction(
            document_type="single_receipt",
            movements=[
                StatementExtractedMovement(
                    transaction_date="2026-09-22",
                    description="Pagamento",
                    amount="30.00",
                    direction="outflow",
                    confidence=0.95,
                    reason=None,
                )
            ],
            reason=None,
        )

        result = _merge_extractions([extraction])

        self.assertEqual(result.document_type, "single_receipt")
        self.assertEqual(len(result.movements), 1)

    def test_missing_api_key_fails_without_external_call(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(StatementDocumentError):
                _analyze_statement_content(
                    text="texto de extrato",
                    images=None,
                )

    def test_invalid_provider_payload_is_rejected_instead_of_invented(self) -> None:
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"movements": []}'))]
        )
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True):
            with patch(
                "backend.services.statement_document_service.OpenAI",
                return_value=client,
            ):
                with self.assertRaises(StatementDocumentError):
                    _analyze_statement_content(
                        text="texto insuficiente",
                        images=None,
                    )

    @staticmethod
    def _completion(extraction: StatementDocumentExtraction) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(extraction.model_dump(mode="json"))
                    )
                )
            ]
        )

    @staticmethod
    def _extraction(*descriptions: str) -> StatementDocumentExtraction:
        return StatementDocumentExtraction(
            document_type="bank_statement",
            reason=None,
            movements=[
                StatementExtractedMovement(
                    transaction_date=f"2026-09-{20 + index:02d}",
                    description=description,
                    amount=f"{40 + index}.00",
                    direction="outflow" if index == 0 else "inflow",
                    confidence=0.98,
                    reason=None,
                )
                for index, description in enumerate(descriptions)
            ],
        )


if __name__ == "__main__":
    unittest.main()
