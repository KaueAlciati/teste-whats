from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

CHATWOOT_URL = os.getenv("CHATWOOT_URL")
CHATWOOT_API_KEY = os.getenv("CHATWOOT_API_KEY")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID")
CHATWOOT_INBOX_ID = os.getenv("CHATWOOT_INBOX_ID")


def _chatwoot_configurado() -> bool:
    return all([CHATWOOT_URL, CHATWOOT_API_KEY, CHATWOOT_ACCOUNT_ID, CHATWOOT_INBOX_ID])


async def transferir_para_vendedor(telefone: str, dados_coletados: dict):
    if not _chatwoot_configurado():
        logger.info("Chatwoot não configurado; transferência para vendedor desativada.")
        return False
    return False
