import os
from datetime import date

from openai import OpenAI

from backend.schemas.financial_intent import FinancialIntent


DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"

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
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise FinancialAIServiceError("Serviço de IA indisponível")

    model = os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
    client = OpenAI(api_key=api_key, timeout=20.0, max_retries=1)

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
        response = client.responses.parse(
            model=model,
            instructions=instructions,
            input=f"Mensagem original: {text}",
            text_format=FinancialIntent,
            store=False,
        )
    except Exception as exc:
        raise FinancialAIServiceError("Falha ao interpretar mensagem") from exc

    if response.output_parsed is None:
        raise FinancialAIServiceError("Resposta estruturada ausente")

    return response.output_parsed
