import base64
import io
import json
import logging
import os
from collections.abc import Iterable

import pymupdf
from openai import APIStatusError, OpenAI, OpenAIError
from pydantic import ValidationError
from pypdf import PdfReader

from backend.schemas.statement_import import StatementDocumentExtraction
from backend.services.image_understanding_service import (
    DEFAULT_VISION_MODEL,
    GROQ_BASE_URL,
)


logger = logging.getLogger("uvicorn.error")

MAX_PDF_PAGES = 12
MAX_IMAGES_PER_REQUEST = 3
MAX_TEXT_CHARS_PER_REQUEST = 60_000
SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}


class StatementDocumentError(RuntimeError):
    pass


def extract_statement_document(
    file_bytes: bytes,
    *,
    mime_type: str,
    filename: str,
) -> StatementDocumentExtraction:
    """Extract statement rows without persisting them.

    This is deliberately independent from HTTP and the WhatsApp receipt flow so
    the same parser can later be called by a WhatsApp statement handler.
    """
    normalized_mime_type = mime_type.casefold().strip()
    if not file_bytes:
        raise StatementDocumentError("Arquivo vazio")

    if normalized_mime_type == "application/pdf":
        return _extract_pdf_statement(file_bytes, filename=filename)
    if normalized_mime_type in SUPPORTED_IMAGE_MIME_TYPES:
        return _extract_image_statement(
            file_bytes,
            mime_type=normalized_mime_type,
            filename=filename,
        )
    raise StatementDocumentError("Formato de extrato não suportado")


def _extract_pdf_statement(
    file_bytes: bytes,
    *,
    filename: str,
) -> StatementDocumentExtraction:
    text_chunks = _extract_pdf_text_chunks(file_bytes)
    if text_chunks:
        logger.info(
            "Extraindo extrato PDF pela camada de texto: arquivo=%s blocos=%s",
            _safe_filename(filename),
            len(text_chunks),
        )
        text_result = _merge_extractions(
            _analyze_statement_content(text=chunk, images=None)
            for chunk in text_chunks
        )
        if text_result.document_type != "unknown" or text_result.movements:
            return text_result

    logger.info(
        "PDF sem movimentações legíveis em texto; usando OCR visual: arquivo=%s",
        _safe_filename(filename),
    )
    rendered_pages = _render_pdf_pages(file_bytes)
    return _merge_extractions(
        _analyze_statement_content(text=None, images=batch)
        for batch in _batched(rendered_pages, MAX_IMAGES_PER_REQUEST)
    )


def _extract_image_statement(
    file_bytes: bytes,
    *,
    mime_type: str,
    filename: str,
) -> StatementDocumentExtraction:
    logger.info(
        "Extraindo extrato por OCR visual: arquivo=%s mime_type=%s bytes=%s",
        _safe_filename(filename),
        mime_type,
        len(file_bytes),
    )
    return _analyze_statement_content(
        text=None,
        images=[(file_bytes, mime_type)],
    )


def _extract_pdf_text_chunks(file_bytes: bytes) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise StatementDocumentError(
                    "PDF protegido por senha não pode ser importado"
                ) from exc
        if len(reader.pages) > MAX_PDF_PAGES:
            raise StatementDocumentError(
                f"O PDF excede o limite de {MAX_PDF_PAGES} páginas"
            )
        page_texts = [
            " ".join((page.extract_text() or "").split())
            for page in reader.pages
        ]
    except StatementDocumentError:
        raise
    except Exception as exc:
        raise StatementDocumentError("Não foi possível ler o PDF") from exc

    meaningful_texts = [text for text in page_texts if len(text) >= 40]
    chunks: list[str] = []
    current = ""
    for page_number, page_text in enumerate(meaningful_texts, start=1):
        labeled = f"\n--- Página {page_number} ---\n{page_text}"
        if current and len(current) + len(labeled) > MAX_TEXT_CHARS_PER_REQUEST:
            chunks.append(current)
            current = ""
        current += labeled
    if current:
        chunks.append(current)
    return chunks


def _render_pdf_pages(file_bytes: bytes) -> list[tuple[bytes, str]]:
    try:
        document = pymupdf.open(stream=file_bytes, filetype="pdf")
        if document.page_count > MAX_PDF_PAGES:
            raise StatementDocumentError(
                f"O PDF excede o limite de {MAX_PDF_PAGES} páginas"
            )
        images: list[tuple[bytes, str]] = []
        for page in document:
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            images.append((pixmap.tobytes("jpeg", jpg_quality=82), "image/jpeg"))
        document.close()
        if not images:
            raise StatementDocumentError("O PDF não possui páginas")
        return images
    except StatementDocumentError:
        raise
    except Exception as exc:
        raise StatementDocumentError("Não foi possível renderizar o PDF") from exc


def _analyze_statement_content(
    *,
    text: str | None,
    images: list[tuple[bytes, str]] | None,
) -> StatementDocumentExtraction:
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_VISION_MODEL", DEFAULT_VISION_MODEL)
    logger.info("GROQ_VISION_MODEL para extrato: %s", model)
    logger.info("GROQ_API_KEY configurada para extrato: %s", bool(api_key))
    if not api_key:
        raise StatementDocumentError("Serviço de leitura de extrato indisponível")

    schema = json.dumps(
        StatementDocumentExtraction.model_json_schema(),
        ensure_ascii=False,
    )
    instructions = f"""
Analise um EXTRATO BANCÁRIO brasileiro ou um COMPROVANTE INDIVIDUAL de PIX,
pagamento ou transferência e retorne apenas JSON compatível com o schema.
Um extrato contém uma lista ou tabela de movimentações de uma conta. Um
comprovante individual deve ser classificado como single_receipt e, quando os
dados estiverem legíveis, deve retornar exatamente uma movement. Documento sem
evidência suficiente deve ser unknown.

Para cada movimentação real do extrato:
- extraia uma linha separada; nunca transforme o arquivo inteiro em uma linha;
- transaction_date em YYYY-MM-DD quando legível; se o ano não estiver na linha,
  use-o somente quando estiver explícito no período/cabeçalho do próprio extrato;
- description deve ser curta e fiel ao texto, sem CPF, conta, agência ou saldo;
- amount deve ser decimal positivo em BRL, sem símbolo nem separador de milhar;
- direction deve ser inflow para entrada/crédito e outflow para saída/débito;
- use unknown e campos null quando a direção ou qualquer dado estiver ilegível;
- não inclua saldo anterior, saldo final, saldo disponível, limite ou totalizador;
- não invente, complete ou estime informação ausente;
- confidence deve refletir somente a legibilidade daquela linha.

Para comprovante individual:
- envio, pagamento ou transferência realizada deve ser outflow;
- recebimento deve ser inflow somente quando isso estiver explícito;
- se não for possível determinar entrada ou saída, use unknown para o usuário
  escolher na prévia;
- não invente dados ausentes nem transforme saldo, tarifa ou total em outra
  movimentação.

JSON Schema:
{schema}
""".strip()

    if images:
        content: str | list[dict] = [{"type": "text", "text": instructions}]
        for image_bytes, mime_type in images:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{encoded}",
                    },
                }
            )
    elif text:
        content = f"{instructions}\n\nTexto extraído do PDF:\n{text}"
    else:
        raise StatementDocumentError("Conteúdo do extrato ausente")

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            timeout=45.0,
            max_retries=1,
        )
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0,
            stream=False,
        )
        output_text = completion.choices[0].message.content
    except APIStatusError as exc:
        logger.error(
            "Erro da Groq ao ler extrato: status HTTP=%s tipo=%s",
            exc.status_code,
            type(exc).__name__,
        )
        raise StatementDocumentError("Falha ao analisar extrato") from exc
    except OpenAIError as exc:
        logger.error(
            "Erro da Groq ao ler extrato: tipo=%s",
            type(exc).__name__,
        )
        raise StatementDocumentError("Falha ao analisar extrato") from exc
    except Exception as exc:
        logger.error(
            "Erro inesperado ao ler extrato: tipo=%s",
            type(exc).__name__,
        )
        raise StatementDocumentError("Falha ao analisar extrato") from exc

    if not isinstance(output_text, str) or not output_text.strip():
        raise StatementDocumentError("Resposta de leitura ausente")
    try:
        return StatementDocumentExtraction.model_validate_json(output_text)
    except (ValidationError, ValueError) as exc:
        logger.error(
            "Resposta inválida ao ler extrato: tipo=%s",
            type(exc).__name__,
        )
        raise StatementDocumentError("Dados extraídos do extrato são inválidos") from exc


def _merge_extractions(
    extractions: Iterable[StatementDocumentExtraction],
) -> StatementDocumentExtraction:
    items = list(extractions)
    movements = [movement for item in items for movement in item.movements]
    if any(item.document_type == "bank_statement" for item in items):
        document_type = "bank_statement"
    elif any(item.document_type == "single_receipt" for item in items):
        document_type = "single_receipt"
    else:
        document_type = "unknown"
    reasons = [item.reason for item in items if item.reason]
    return StatementDocumentExtraction(
        document_type=document_type,
        movements=movements,
        reason="; ".join(reasons)[:500] or None,
    )


def _batched(
    items: list[tuple[bytes, str]],
    size: int,
) -> Iterable[list[tuple[bytes, str]]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _safe_filename(filename: str) -> str:
    return os.path.basename(filename).replace("\n", " ").replace("\r", " ")[:120]
