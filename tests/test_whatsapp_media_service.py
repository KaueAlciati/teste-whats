import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from backend.services.whatsapp_media_service import (
    MAX_AUDIO_BYTES,
    WhatsAppMediaTooLargeError,
    download_whatsapp_media,
)


class WhatsAppMediaServiceTestCase(unittest.TestCase):
    def test_downloads_media_bytes_with_meta_authorization(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(
                request.headers.get("authorization"),
                "Bearer test-token",
            )
            if request.url.host == "graph.facebook.com":
                return httpx.Response(
                    200,
                    json={
                        "url": "https://lookaside.example/audio",
                        "mime_type": "audio/ogg; codecs=opus",
                        "file_size": 11,
                    },
                )
            return httpx.Response(200, content=b"audio-bytes")

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.dict(
            os.environ,
            {"WHATSAPP_TOKEN": "test-token"},
            clear=True,
        ):
            with patch(
                "backend.services.whatsapp_media_service.httpx.AsyncClient",
                return_value=client,
            ):
                media = asyncio.run(
                    download_whatsapp_media(
                        "media-id",
                        fallback_mime_type="audio/ogg",
                    )
                )

        self.assertEqual(media.content, b"audio-bytes")
        self.assertEqual(media.mime_type, "audio/ogg")
        self.assertEqual(media.filename, "audio.ogg")
        self.assertEqual(len(requests), 2)

    def test_rejects_audio_larger_than_limit_before_download(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.example/audio",
                    "mime_type": "audio/ogg",
                    "file_size": MAX_AUDIO_BYTES + 1,
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.dict(
            os.environ,
            {"WHATSAPP_TOKEN": "test-token"},
            clear=True,
        ):
            with patch(
                "backend.services.whatsapp_media_service.httpx.AsyncClient",
                return_value=client,
            ):
                with self.assertRaises(WhatsAppMediaTooLargeError):
                    asyncio.run(download_whatsapp_media("large-media-id"))

        self.assertEqual(len(requests), 1)


if __name__ == "__main__":
    unittest.main()
