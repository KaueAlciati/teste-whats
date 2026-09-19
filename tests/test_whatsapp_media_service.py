import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from backend.services.whatsapp_media_service import (
    MAX_AUDIO_BYTES,
    MAX_IMAGE_BYTES,
    WhatsAppMediaTooLargeError,
    WhatsAppMediaUnsupportedTypeError,
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

    def test_downloads_and_validates_image(self) -> None:
        image_bytes = b"\x89PNG\r\n\x1a\n" + b"image-content"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "graph.facebook.com":
                return httpx.Response(
                    200,
                    json={
                        "url": "https://lookaside.example/image",
                        "mime_type": "image/png",
                        "file_size": len(image_bytes),
                    },
                )
            return httpx.Response(
                200,
                content=image_bytes,
                headers={"content-type": "image/png"},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.dict(os.environ, {"WHATSAPP_TOKEN": "test-token"}, clear=True):
            with patch(
                "backend.services.whatsapp_media_service.httpx.AsyncClient",
                return_value=client,
            ):
                media = asyncio.run(
                    download_whatsapp_media(
                        "image-media-id",
                        media_kind="image",
                    )
                )

        self.assertEqual(media.content, image_bytes)
        self.assertEqual(media.mime_type, "image/png")
        self.assertEqual(media.filename, "image.png")

    def test_accepts_jpeg_and_webp_images(self) -> None:
        supported_images = (
            ("image/jpeg", b"\xff\xd8\xffimage", "image.jpg"),
            ("image/webp", b"RIFF\x04\x00\x00\x00WEBPimage", "image.webp"),
        )

        for mime_type, image_bytes, expected_filename in supported_images:
            with self.subTest(mime_type=mime_type):
                def handler(request: httpx.Request) -> httpx.Response:
                    if request.url.host == "graph.facebook.com":
                        return httpx.Response(
                            200,
                            json={
                                "url": "https://lookaside.example/image",
                                "mime_type": mime_type,
                                "file_size": len(image_bytes),
                            },
                        )
                    return httpx.Response(
                        200,
                        content=image_bytes,
                        headers={"content-type": mime_type},
                    )

                client = httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)
                )
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
                                f"{mime_type}-id",
                                media_kind="image",
                            )
                        )

                self.assertEqual(media.mime_type, mime_type)
                self.assertEqual(media.filename, expected_filename)

    def test_rejects_image_larger_than_ten_megabytes(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.example/image",
                    "mime_type": "image/jpeg",
                    "file_size": MAX_IMAGE_BYTES + 1,
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.dict(os.environ, {"WHATSAPP_TOKEN": "test-token"}, clear=True):
            with patch(
                "backend.services.whatsapp_media_service.httpx.AsyncClient",
                return_value=client,
            ):
                with self.assertRaises(WhatsAppMediaTooLargeError):
                    asyncio.run(
                        download_whatsapp_media(
                            "large-image-id",
                            media_kind="image",
                        )
                    )

    def test_rejects_unexpected_image_mime_type(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "url": "https://lookaside.example/file",
                    "mime_type": "application/x-msdownload",
                    "file_size": 100,
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.dict(os.environ, {"WHATSAPP_TOKEN": "test-token"}, clear=True):
            with patch(
                "backend.services.whatsapp_media_service.httpx.AsyncClient",
                return_value=client,
            ):
                with self.assertRaises(WhatsAppMediaUnsupportedTypeError):
                    asyncio.run(
                        download_whatsapp_media(
                            "invalid-image-id",
                            media_kind="image",
                        )
                    )


if __name__ == "__main__":
    unittest.main()
