import base64
import logging
import os
from datetime import date

from openai import APIStatusError, OpenAI, OpenAIError

from backend.schemas.receipt_extraction import ReceiptExtraction


logger = logging.getLogger("uvicorn.error")

DEFAULT_VISION_MODEL = "qwen/qwen3.6-27b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ImageUnderstandingError(RuntimeError):
    pass


def analyze_receipt_image(
    image_bytes: bytes,
    *,
    mime_type: str,
    current_date: date,
    caption: str | None = None,
    user_name: str | None = None,
) -> ReceiptExtraction:
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_VISION_MODEL", DEFAULT_VISION_MODEL)
    normalized_mime_type = mime_type.casefold().strip()

    logger.info("GROQ_VISION_MODEL: %s", model)
    logger.info("GROQ_API_KEY configurada para visão: %s", bool(api_key))

    if not api_key:
        raise ImageUnderstandingError("Serviço de visão indisponível")
    if normalized_mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ImageUnderstandingError("Formato de imagem não suportado")
    if not image_bytes:
        raise ImageUnderstandingError("Imagem vazia")

    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{normalized_mime_type};base64,{encoded_image}"
    safe_caption = " ".join((caption or "").split())[:500] or "Sem legenda."
    safe_user_name = " ".join((user_name or "").split())[:120] or "Não informado."

    instructions = f"""
Analise uma única imagem como possível documento financeiro brasileiro e retorne
somente os dados do schema. A data atual é {current_date.isoformat()}.

Prioridades:
- identifique o valor TOTAL da transação, nunca o saldo da conta nem uma taxa;
- identifique data, horário, pagador, destinatário e instituições quando legíveis;
- diferencie PIX, transferência, pagamento, compra e imagem de fatura;
- use amount como string decimal, sem símbolo de moeda e sem separador de milhar;
- use currency=BRL somente quando houver evidência de reais; caso contrário, null;
- não invente campos ilegíveis: use null;
- gere description curta, sem CPF, CNPJ, conta, agência, chave PIX ou código;
- sugira categoria somente quando houver evidência clara; caso contrário, Outros.

Direção:
- outflow somente quando a imagem ou legenda indicar pagamento/envio feito pelo usuário;
- inflow somente quando indicar recebimento pelo usuário;
- unknown quando não estiver claro, com requires_confirmation=true.
Considere rótulos como "Você pagou", "Pagamento realizado", "Transferência enviada",
"Recebido" e "PIX recebido". O nome conhecido do usuário é: {safe_user_name}

Status:
- completed apenas para transação concluída;
- pending, scheduled, cancelled ou refunded quando houver essa indicação;
- unknown se não estiver legível.
Somente uma transação concluída, única e clara pode dispensar confirmação.
Print de saldo/extrato, QR Code sem pagamento concluído, imagem genérica, ilegível,
agendada, cancelada, pendente, devolvida ou estornada deve exigir confirmação ou ser
classificada como unknown, sem inventar uma transação.
""".strip()

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            timeout=30.0,
            max_retries=1,
        )
        response = client.responses.parse(
            model=model,
            instructions=instructions,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Legenda enviada com a imagem: {safe_caption}",
                        },
                        {
                            "type": "input_image",
                            "image_url": data_url,
                            "detail": "high",
                        },
                    ],
                }
            ],
            text_format=ReceiptExtraction,
        )
    except APIStatusError as exc:
        logger.error(
            "Erro da visão Groq: status HTTP=%s; tipo=%s",
            exc.status_code,
            type(exc).__name__,
        )
        raise ImageUnderstandingError("Falha ao analisar imagem") from exc
    except OpenAIError as exc:
        logger.error("Erro da visão Groq: tipo=%s", type(exc).__name__)
        raise ImageUnderstandingError("Falha ao analisar imagem") from exc
    except Exception as exc:
        logger.error("Erro da visão Groq: tipo=%s", type(exc).__name__)
        raise ImageUnderstandingError("Falha ao analisar imagem") from exc

    if response.output_parsed is None:
        raise ImageUnderstandingError("Resposta estruturada ausente")

    extraction = response.output_parsed
    logger.info(
        "Análise de comprovante concluída: confidence=%.2f direction=%s "
        "requires_confirmation=%s",
        extraction.confidence,
        extraction.direction,
        extraction.requires_confirmation,
    )
    return extraction
