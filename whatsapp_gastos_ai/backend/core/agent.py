from __future__ import annotations

import logging

from backend.core.models import AgentResponse, IncomingMessage
from backend.core.router import route_incoming_message
from backend.core.sessions import session_store

logger = logging.getLogger(__name__)


async def process_agent_message(message: IncomingMessage) -> AgentResponse:
    session = session_store.get(message.channel, message.user_id)
    session.state["channel"] = message.channel
    session.state["user_id"] = message.user_id
    if message.text:
        session.state["last_text"] = message.text

    logger.info("Mensagem recebida [%s] [%s] tipo=%s", message.channel, message.user_id, message.message_type)

    response = await route_incoming_message(message, session)
    session.state["last_response_type"] = response.response_type
    return response
