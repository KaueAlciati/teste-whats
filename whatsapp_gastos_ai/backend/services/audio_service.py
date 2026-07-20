from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


async def transcrever_audio(caminho_arquivo: str) -> str | None:
    """
    Transcreve um áudio usando a API da OpenAI, se configurada.
    Retorna None quando a funcionalidade não estiver disponível.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.info("OPENAI_API_KEY ausente; transcrição desativada.")
        return None

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        arquivo = Path(caminho_arquivo)
        if not arquivo.exists():
            logger.warning("Arquivo de áudio não encontrado: %s", caminho_arquivo)
            return None

        with arquivo.open("rb") as stream:
            resultado = await client.audio.transcriptions.create(
                model="whisper-1",
                file=stream,
            )
        texto = getattr(resultado, "text", None)
        logger.info("Transcrição concluída.")
        return texto
    except Exception as exc:
        logger.exception("Erro ao transcrever áudio: %s", exc)
        return None
