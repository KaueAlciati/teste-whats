import logging
import os
from datetime import date

from openai import APIStatusError, OpenAI, OpenAIError

from backend.schemas.financial_intent import FinancialIntent


logger = logging.getLogger("uvicorn.error")

DEFAULT_AI_MODEL = "openai/gpt-oss-20b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

EXPENSE_CATEGORIES = (
    "Alimentação",
    "Transporte",
    "Moradia",
    "Saúde",
    "Educação",
    "Lazer",
    "Compras",
    "Assinaturas",
    "Contas",
    "Impostos",
    "Outros",
)

INCOME_CATEGORIES = (
    "Salário",
    "Freelance",
    "Venda",
    "Investimentos",
    "Reembolso",
    "Outros",
)


class FinancialAIServiceError(RuntimeError):
    pass


def interpret_financial_message(
    text: str,
    current_date: date,
) -> FinancialIntent:
    api_key = os.getenv("GROQ_API_KEY")
    provider = os.getenv("AI_PROVIDER", "groq")
    model = os.getenv("AI_MODEL", DEFAULT_AI_MODEL)

    logger.info("AI_PROVIDER: %s", provider)
    logger.info("AI_MODEL: %s", model)
    logger.info("GROQ_API_KEY configurada: %s", bool(api_key))

    if not api_key:
        raise FinancialAIServiceError("Serviço de IA indisponível")

    instructions = f"""
Você interpreta mensagens financeiras pessoais escritas em português do Brasil.
Sua única tarefa é classificar e extrair dados para o schema fornecido.
Nunca calcule saldo, nunca execute operações e nunca invente valores ausentes.

A data atual é {current_date.isoformat()}.
Converta datas relativas como hoje, ontem, anteontem e dias da semana para YYYY-MM-DD.
Quando uma criação não mencionar data, use a data atual.

Categorias de despesa permitidas: {", ".join(EXPENSE_CATEGORIES)}.
Categorias de receita permitidas: {", ".join(INCOME_CATEGORIES)}.
Sugira somente uma dessas categorias. Se nenhuma combinar, use Outros.

Ações permitidas:
- create_expense para gastos e pagamentos;
- create_income para dinheiro recebido;
- query_balance para saldo atual;
- query_expenses para total de gastos;
- query_income para total de receitas;
- unknown para mensagens não financeiras.

Períodos permitidos: today, yesterday, current_week, current_month,
previous_month e all. Para consultas sem período explícito, use all.
Se faltar valor ou outra informação essencial para criar uma movimentação,
marque needs_clarification como true e formule uma pergunta curta em pt-BR.
""".strip()

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            timeout=20.0,
            max_retries=1,
        )
        response = client.responses.parse(
            model=model,
            instructions=instructions,
            input=f"Mensagem original: {text}",
            text_format=FinancialIntent,
        )
    except APIStatusError as exc:
        logger.error(
            "Erro da Groq: status HTTP=%s; tipo=%s",
            exc.status_code,
            type(exc).__name__,
        )
        raise FinancialAIServiceError("Falha ao interpretar mensagem") from exc
    except OpenAIError as exc:
        logger.error("Erro da Groq: tipo=%s", type(exc).__name__)
        raise FinancialAIServiceError("Falha ao interpretar mensagem") from exc
    except Exception as exc:
        logger.error("Erro da Groq: tipo=%s", type(exc).__name__)
        raise FinancialAIServiceError("Falha ao interpretar mensagem") from exc

    if response.output_parsed is None:
        raise FinancialAIServiceError("Resposta estruturada ausente")

    return response.output_parsed
