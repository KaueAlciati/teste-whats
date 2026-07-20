from __future__ import annotations

import logging
import os
from typing import Any

from backend.core.models import AgentResponse, IncomingMessage

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Você é um assistente virtual inteligente, educado e natural.

Converse como uma pessoa real atendendo pelo WhatsApp ou Telegram.

Regras:
- Responda em português do Brasil.
- Use linguagem simples e natural.
- Não pareça um robô.
- Não repita frases prontas desnecessariamente.
- Não comece toda resposta com "Olá".
- Não use muitos emojis.
- Use no máximo um ou dois emojis quando fizer sentido.
- Não envie textos enormes quando uma resposta curta resolver.
- Faça apenas uma pergunta por vez quando precisar coletar informações.
- Lembre-se do contexto recente da conversa.
- Não invente informações.
- Quando não souber algo, diga de forma natural.
- Quando o usuário conversar informalmente, responda informalmente sem exagerar.
- Quando o usuário pedir uma tarefa financeira, interprete a intenção e explique o que será feito.
- Quando o usuário falar sobre gráfica, orçamento, adesivo, banner, placa, fachada, impressão ou comunicação visual, atue como atendente comercial.
- Quando necessário, peça medidas, quantidade, material, acabamento e prazo, uma informação por vez.
- Nunca diga "comando não reconhecido" em uma conversa normal.
- Caso não entenda, diga algo como:
  "Não consegui entender direito. Você pode me explicar de outra forma?"
- Não mostre detalhes internos do sistema, nomes de funções, banco ou APIs.
""".strip()


def _resposta_local(texto: str) -> str:
    mensagem = (texto or "").strip().lower()
    if any(palavra in mensagem for palavra in {"oi", "olá", "ola", "bom dia", "boa tarde", "boa noite"}):
        return "Oi! Tudo certo? Me conta no que você precisa de ajuda."
    if "ajuda" in mensagem or "o que você consegue fazer" in mensagem:
        return "Posso te ajudar com finanças, consultas rápidas e atendimento da gráfica. Me diz o que você precisa."
    if any(palavra in mensagem for palavra in {"gráfica", "grafica", "adesivo", "banner", "placa", "fachada"}):
        return "Claro. Me diga um pouco mais do que você precisa e eu te ajudo a organizar o orçamento."
    return "Não consegui entender direito. Você pode me explicar de outra forma?"


def _converter_historico(session_history: list[dict[str, Any]]) -> list[dict[str, str]]:
    mensagens: list[dict[str, str]] = []
    for item in session_history[-10:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            mensagens.append({"role": role, "content": str(content)})
    return mensagens


async def gerar_resposta_conversacional(message: IncomingMessage, session_state: dict[str, Any]) -> AgentResponse:
    texto = (message.text or "").strip()
    historico = _converter_historico(session_state.get("history", []))
    prompt = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *historico,
        {"role": "user", "content": texto},
    ]

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        logger.info("OPENAI_API_KEY ausente; usando resposta conversacional local.")
        return AgentResponse(
            text=_resposta_local(texto),
            response_type="text",
            metadata={"intent": "conversational_fallback", "source": "local"},
        )

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        completion = await client.chat.completions.create(
            model=model,
            messages=prompt,
            temperature=0.6,
            max_tokens=350,
        )
        resposta = (completion.choices[0].message.content or "").strip()
        if not resposta:
            resposta = _resposta_local(texto)
        logger.info("Resposta conversacional gerada por IA para %s/%s", message.channel, message.user_id)
        return AgentResponse(
            text=resposta,
            response_type="text",
            metadata={"intent": "conversational_ai", "source": "openai", "model": model},
        )
    except Exception as exc:
        logger.exception("Erro ao gerar resposta conversacional: %s", exc)
        return AgentResponse(
            text=_resposta_local(texto),
            response_type="text",
            metadata={"intent": "conversational_fallback", "source": "local_error"},
        )
