import asyncio
import json
import os
import unittest
from unittest.mock import patch

import httpx

from backend.services.whatsapp_service import send_document_message


class WhatsAppDocumentServiceTestCase(unittest.TestCase):
    def test_uploads_and_sends_document_without_real_meta_call(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(
                request.headers.get("authorization"),
                "Bearer test-token",
            )
            if request.url.path.endswith("/media"):
                self.assertIn(
                    b'extrato-fincontrol-2026-09.xlsx',
                    request.content,
                )
                self.assertIn(b"xlsx-content", request.content)
                return httpx.Response(200, json={"id": "meta-media-id"})

            payload = json.loads(request.content)
            self.assertEqual(payload["to"], "5515999999999")
            self.assertEqual(payload["type"], "document")
            self.assertEqual(payload["document"]["id"], "meta-media-id")
            self.assertEqual(
                payload["document"]["filename"],
                "extrato-fincontrol-2026-09.xlsx",
            )
            return httpx.Response(200, json={"messages": [{"id": "wamid.sent"}]})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with (
            patch.dict(
                os.environ,
                {
                    "WHATSAPP_TOKEN": "test-token",
                    "PHONE_NUMBER_ID": "phone-id",
                },
                clear=True,
            ),
            patch(
                "backend.services.whatsapp_service.httpx.AsyncClient",
                return_value=client,
            ),
        ):
            sent = asyncio.run(
                send_document_message(
                    "5515999999999",
                    content=b"xlsx-content",
                    filename="extrato-fincontrol-2026-09.xlsx",
                    mime_type=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    caption="Extrato FinControl AI · 09/2026",
                )
            )

        self.assertTrue(sent)
        self.assertEqual(len(requests), 2)
        self.assertTrue(requests[0].url.path.endswith("/phone-id/media"))
        self.assertTrue(requests[1].url.path.endswith("/phone-id/messages"))


if __name__ == "__main__":
    unittest.main()
