import json
import logging
import os

from openai import APIStatusError, OpenAI, OpenAIError

from backend.schemas.insights import AIInsightsContent


logger = logging.getLogger("uvicorn.error")

DEFAULT_AI_MODEL = "openai/gpt-oss-20b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class InsightsAIServiceError(RuntimeError):
    pass


def generate_ai_insights(payload: dict) -> AIInsightsContent:
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("AI_MODEL", DEFAULT_AI_MODEL)
    logger.info("Insights AI_PROVIDER: groq")
    logger.info("Insights AI_MODEL: %s", model)
    logger.info("Insights GROQ_API_KEY configurada: %s", bool(api_key))
    if not api_key:
        raise InsightsAIServiceError("Serviço de IA indisponível")

    instructions = """
Você é um assistente educacional de organização financeira pessoal.
Responda em português do Brasil, com tom natural, objetivo, profissional e
não alarmista.

REGRAS OBRIGATÓRIAS:
- Use somente os dados presentes no payload recebido.
- Não recalcule, substitua ou invente números.
- Não presuma renda, dívidas, investimentos, patrimônio ou metas ausentes.
- Quando faltarem dados, sinalize a limitação com clareza.
- Recomendações devem ser proporcionais aos registros disponíveis.
- Não prometa rentabilidade e não ordene compra ou venda de ativo específico.
- O perfil de risco é apenas uma preferência declarada, não suitability.
- Próximos passos devem ter entre 3 e 5 ações curtas e realizáveis.
- Sugestões de corte só podem mencionar valores quando eles estiverem no payload.
""".strip()

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            timeout=25.0,
            max_retries=1,
        )
        response = client.responses.parse(
            model=model,
            instructions=instructions,
            input=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            text_format=AIInsightsContent,
        )
    except APIStatusError as exc:
        logger.error(
            "Erro da Groq nos insights: status HTTP=%s; tipo=%s",
            exc.status_code,
            type(exc).__name__,
        )
        raise InsightsAIServiceError("Falha ao gerar análise") from exc
    except OpenAIError as exc:
        logger.error("Erro da Groq nos insights: tipo=%s", type(exc).__name__)
        raise InsightsAIServiceError("Falha ao gerar análise") from exc
    except Exception as exc:
        logger.error("Erro da Groq nos insights: tipo=%s", type(exc).__name__)
        raise InsightsAIServiceError("Falha ao gerar análise") from exc

    if response.output_parsed is None:
        raise InsightsAIServiceError("Resposta estruturada ausente")
    return response.output_parsed
