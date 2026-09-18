import logging
import os
from dataclasses import dataclass
from urllib.parse import quote

import httpx


logger = logging.getLogger("uvicorn.error")

GRAPH_API_VERSION = "v25.0"
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MEDIA_METADATA_TIMEOUT_SECONDS = 10.0
MEDIA_DOWNLOAD_TIMEOUT_SECONDS = 30.0


class WhatsAppMediaError(RuntimeError):
    pass


class WhatsAppMediaTooLargeError(WhatsAppMediaError):
    pass


@dataclass(frozen=True)
class WhatsAppMedia:
    content: bytes
    mime_type: str
    filename: str


async def download_whatsapp_media(
    media_id: str,
    *,
    fallback_mime_type: str | None = None,
) -> WhatsAppMedia:
    token = os.getenv("WHATSAPP_TOKEN")
    if not token:
        logger.error("WHATSAPP_TOKEN configurado para mídia: False")
        raise WhatsAppMediaError("Configuração de mídia indisponível")

    safe_media_id = quote(media_id, safe="")
    metadata_url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{safe_media_id}"
    )
    authorization = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        metadata = await _fetch_metadata(
            client,
            metadata_url=metadata_url,
            headers=authorization,
        )

        media_url = metadata.get("url")
        if not isinstance(media_url, str) or not media_url:
            raise WhatsAppMediaError("URL de mídia ausente")

        declared_size = _parse_size(metadata.get("file_size"))
        if declared_size is not None and declared_size > MAX_AUDIO_BYTES:
            raise WhatsAppMediaTooLargeError("Áudio excede o tamanho máximo")

        mime_type = _normalize_mime_type(
            metadata.get("mime_type"),
            fallback_mime_type,
        )
        content = await _download_limited(
            client,
            media_url=media_url,
            headers=authorization,
        )

    return WhatsAppMedia(
        content=content,
        mime_type=mime_type,
        filename=_filename_for_mime_type(mime_type),
    )


async def _fetch_metadata(
    client: httpx.AsyncClient,
    *,
    metadata_url: str,
    headers: dict[str, str],
) -> dict[str, object]:
    try:
        response = await client.get(
            metadata_url,
            headers=headers,
            timeout=MEDIA_METADATA_TIMEOUT_SECONDS,
        )
    except httpx.RequestError as exc:
        logger.error("Falha ao consultar mídia da Meta: tipo=%s", type(exc).__name__)
        raise WhatsAppMediaError("Falha ao consultar mídia") from exc

    if response.is_error:
        logger.error(
            "Falha ao consultar mídia da Meta: status HTTP=%s",
            response.status_code,
        )
        raise WhatsAppMediaError("Falha ao consultar mídia")

    try:
        payload = response.json()
    except ValueError as exc:
        raise WhatsAppMediaError("Resposta de mídia inválida") from exc

    if not isinstance(payload, dict):
        raise WhatsAppMediaError("Resposta de mídia inválida")
    return payload


async def _download_limited(
    client: httpx.AsyncClient,
    *,
    media_url: str,
    headers: dict[str, str],
) -> bytes:
    chunks: list[bytes] = []
    downloaded_size = 0

    try:
        async with client.stream(
            "GET",
            media_url,
            headers=headers,
            timeout=MEDIA_DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            if response.is_error:
                logger.error(
                    "Falha ao baixar mídia da Meta: status HTTP=%s",
                    response.status_code,
                )
                raise WhatsAppMediaError("Falha ao baixar mídia")

            content_length = _parse_size(response.headers.get("content-length"))
            if content_length is not None and content_length > MAX_AUDIO_BYTES:
                raise WhatsAppMediaTooLargeError(
                    "Áudio excede o tamanho máximo"
                )

            async for chunk in response.aiter_bytes():
                downloaded_size += len(chunk)
                if downloaded_size > MAX_AUDIO_BYTES:
                    raise WhatsAppMediaTooLargeError(
                        "Áudio excede o tamanho máximo"
                    )
                chunks.append(chunk)
    except WhatsAppMediaError:
        raise
    except httpx.RequestError as exc:
        logger.error("Falha ao baixar mídia da Meta: tipo=%s", type(exc).__name__)
        raise WhatsAppMediaError("Falha ao baixar mídia") from exc

    content = b"".join(chunks)
    if not content:
        raise WhatsAppMediaError("Mídia vazia")
    return content


def _normalize_mime_type(
    metadata_mime_type: object,
    fallback_mime_type: str | None,
) -> str:
    candidate = (
        metadata_mime_type
        if isinstance(metadata_mime_type, str)
        else fallback_mime_type
    )
    if not candidate:
        return "application/octet-stream"
    return candidate.split(";", 1)[0].strip().casefold()


def _filename_for_mime_type(mime_type: str) -> str:
    extensions = {
        "audio/flac": ".flac",
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/mpga": ".mpga",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/webm": ".webm",
    }
    return f"audio{extensions.get(mime_type, '.ogg')}"


def _parse_size(value: object) -> int | None:
    try:
        parsed = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return parsed if parsed is not None and parsed >= 0 else None
