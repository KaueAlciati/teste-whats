import logging
import os

from openai import APIStatusError, AsyncOpenAI, OpenAIError

from backend.services.ai_financial_service import GROQ_BASE_URL


logger = logging.getLogger("uvicorn.error")

DEFAULT_TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"
TRANSCRIPTION_TIMEOUT_SECONDS = 60.0


class AudioTranscriptionError(RuntimeError):
    pass


async def transcribe_audio(
    audio_content: bytes,
    *,
    filename: str,
    mime_type: str,
) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv(
        "GROQ_TRANSCRIPTION_MODEL",
        DEFAULT_TRANSCRIPTION_MODEL,
    )

    logger.info("GROQ_TRANSCRIPTION_MODEL: %s", model)
    logger.info("GROQ_API_KEY configurada para transcrição: %s", bool(api_key))

    if not api_key:
        raise AudioTranscriptionError("Serviço de transcrição indisponível")
    if not audio_content:
        return ""

    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            timeout=TRANSCRIPTION_TIMEOUT_SECONDS,
            max_retries=1,
        )
        try:
            transcription = await client.audio.transcriptions.create(
                file=(filename, audio_content, mime_type),
                model=model,
                language="pt",
                temperature=0,
                response_format="json",
            )
        finally:
            await client.close()
    except APIStatusError as exc:
        logger.error(
            "Erro de transcrição da Groq: status HTTP=%s; tipo=%s",
            exc.status_code,
            type(exc).__name__,
        )
        raise AudioTranscriptionError("Falha ao transcrever áudio") from exc
    except OpenAIError as exc:
        logger.error(
            "Erro de transcrição da Groq: tipo=%s",
            type(exc).__name__,
        )
        raise AudioTranscriptionError("Falha ao transcrever áudio") from exc
    except Exception as exc:
        logger.error(
            "Erro de transcrição da Groq: tipo=%s",
            type(exc).__name__,
        )
        raise AudioTranscriptionError("Falha ao transcrever áudio") from exc

    text = getattr(transcription, "text", "")
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())
