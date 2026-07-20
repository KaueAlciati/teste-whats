from __future__ import annotations

import logging

from backend.core.models import AgentResponse, IncomingMessage
from backend.core.router import route_incoming_message
from backend.core.sessions import session_store
from backend.services.conversation_service import carregar_historico_conversa, salvar_mensagem_conversa

logger = logging.getLogger(__name__)


async def process_agent_message(message: IncomingMessage) -> AgentResponse:
    session = session_store.get(message.channel, message.user_id)
    session.state["channel"] = message.channel
    session.state["user_id"] = message.user_id
    session.state.setdefault("collected_data", {})
    session.state.setdefault("current_intent", None)

    if not session.state.get("history_loaded"):
        session.state["history"] = carregar_historico_conversa(session.session_id, message.channel, limite=20)
        session.state["history_loaded"] = True

    conteudo_usuario = message.text or message.file_name or message.media_id or f"[{message.message_type}]"
    if message.text:
        session.state["last_text"] = message.text
    session_store.append_history(
        message.channel,
        message.user_id,
        role="user",
        content=conteudo_usuario,
        message_type=message.message_type,
        metadata=message.metadata,
    )
    salvar_mensagem_conversa(session.session_id, message.channel, "user", message.message_type, conteudo_usuario)

    logger.info("Mensagem recebida [%s] [%s] tipo=%s", message.channel, message.user_id, message.message_type)

    response = await route_incoming_message(message, session)
    session.state["last_response_type"] = response.response_type
    conteudo_assistente = response.text or response.response_type
    session_store.append_history(
        message.channel,
        message.user_id,
        role="assistant",
        content=conteudo_assistente,
        message_type=response.response_type,
        metadata=response.metadata,
    )
    salvar_mensagem_conversa(session.session_id, message.channel, "assistant", response.response_type, conteudo_assistente)
    session.state["last_response"] = response.text
    logger.info("Resposta gerada [%s] [%s] intent=%s", message.channel, message.user_id, response.metadata.get("intent"))
    return response
