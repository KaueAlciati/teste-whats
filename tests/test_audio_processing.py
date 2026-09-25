import asyncio
import unittest
from unittest.mock import AsyncMock, call, patch

from backend.services.conversation_service import (
    audio_empty_response,
    audio_error_response,
    audio_too_large_response,
)
from backend.services.financial_assistant_service import (
    process_financial_audio_message,
)
from backend.services.whatsapp_media_service import (
    WhatsAppMedia,
    WhatsAppMediaError,
    WhatsAppMediaTooLargeError,
)
from backend.services.audio_transcription_service import AudioTranscriptionError


class AudioProcessingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.media = WhatsAppMedia(
            content=b"audio-bytes",
            mime_type="audio/ogg",
            filename="audio.ogg",
        )

    def test_transcription_enters_existing_financial_flow(self) -> None:
        send_mock = AsyncMock(return_value=True)
        process_mock = AsyncMock(return_value=None)

        with (
            patch(
                "backend.services.financial_assistant_service._message_already_processed",
                return_value=False,
            ),
            patch(
                "backend.services.financial_assistant_service.download_whatsapp_media",
                AsyncMock(return_value=self.media),
            ) as download_mock,
            patch(
                "backend.services.financial_assistant_service.transcribe_audio",
                AsyncMock(return_value="gastei 80 reais de diesel hoje"),
            ) as transcribe_mock,
            patch(
                "backend.services.financial_assistant_service.process_financial_message",
                process_mock,
            ),
            patch(
                "backend.services.financial_assistant_service.send_text_message",
                send_mock,
            ),
        ):
            asyncio.run(
                process_financial_audio_message(
                    "5515999999999",
                    "wamid.audio",
                    "media-id",
                    "audio/ogg",
                )
            )

        download_mock.assert_awaited_once_with(
            "media-id",
            fallback_mime_type="audio/ogg",
        )
        transcribe_mock.assert_awaited_once_with(
            b"audio-bytes",
            filename="audio.ogg",
            mime_type="audio/ogg",
        )
        process_mock.assert_awaited_once_with(
            "5515999999999",
            "wamid.audio",
            "gastei 80 reais de diesel hoje",
            source="whatsapp_audio",
            audio_transcription="gastei 80 reais de diesel hoje",
        )
        send_mock.assert_not_awaited()

    def test_goal_transcription_enters_the_same_message_flow(self) -> None:
        send_mock = AsyncMock(return_value=True)
        process_mock = AsyncMock(return_value=None)

        with self._audio_patches(
            transcription="Mostra minhas metas.",
            send_mock=send_mock,
            process_mock=process_mock,
        ):
            asyncio.run(
                process_financial_audio_message(
                    "5515999999999",
                    "wamid.audio-goals",
                    "media-id",
                    "audio/ogg",
                )
            )

        process_mock.assert_awaited_once_with(
            "5515999999999",
            "wamid.audio-goals",
            "Mostra minhas metas.",
            source="whatsapp_audio",
            audio_transcription="Mostra minhas metas.",
        )

    def test_empty_transcription_does_not_enter_financial_flow(self) -> None:
        send_mock = AsyncMock(return_value=True)
        process_mock = AsyncMock(return_value=None)

        with self._audio_patches(
            transcription="   ",
            send_mock=send_mock,
            process_mock=process_mock,
        ):
            asyncio.run(
                process_financial_audio_message(
                    "5515999999999",
                    "wamid.empty",
                    "media-id",
                    "audio/ogg",
                )
            )

        process_mock.assert_not_awaited()
        self.assertEqual(send_mock.await_count, 1)
        self.assertEqual(
            send_mock.await_args_list[-1],
            call("5515999999999", audio_empty_response()),
        )

    def test_download_error_is_handled(self) -> None:
        send_mock = AsyncMock(return_value=True)
        process_mock = AsyncMock(return_value=None)

        with (
            patch(
                "backend.services.financial_assistant_service._message_already_processed",
                return_value=False,
            ),
            patch(
                "backend.services.financial_assistant_service.download_whatsapp_media",
                AsyncMock(side_effect=WhatsAppMediaError("download failed")),
            ),
            patch(
                "backend.services.financial_assistant_service.process_financial_message",
                process_mock,
            ),
            patch(
                "backend.services.financial_assistant_service.send_text_message",
                send_mock,
            ),
        ):
            asyncio.run(
                process_financial_audio_message(
                    "5515999999999",
                    "wamid.download-error",
                    "media-id",
                    "audio/ogg",
                )
            )

        process_mock.assert_not_awaited()
        self.assertEqual(
            send_mock.await_args_list[-1],
            call("5515999999999", audio_error_response()),
        )

    def test_transcription_error_is_handled(self) -> None:
        send_mock = AsyncMock(return_value=True)
        process_mock = AsyncMock(return_value=None)

        with self._audio_patches(
            transcription_error=AudioTranscriptionError("groq unavailable"),
            send_mock=send_mock,
            process_mock=process_mock,
        ):
            asyncio.run(
                process_financial_audio_message(
                    "5515999999999",
                    "wamid.transcription-error",
                    "media-id",
                    "audio/ogg",
                )
            )

        process_mock.assert_not_awaited()
        self.assertEqual(
            send_mock.await_args_list[-1],
            call("5515999999999", audio_error_response()),
        )

    def test_large_audio_receives_natural_limit_message(self) -> None:
        send_mock = AsyncMock(return_value=True)
        process_mock = AsyncMock(return_value=None)

        with (
            patch(
                "backend.services.financial_assistant_service._message_already_processed",
                return_value=False,
            ),
            patch(
                "backend.services.financial_assistant_service.download_whatsapp_media",
                AsyncMock(
                    side_effect=WhatsAppMediaTooLargeError("audio too large")
                ),
            ),
            patch(
                "backend.services.financial_assistant_service.process_financial_message",
                process_mock,
            ),
            patch(
                "backend.services.financial_assistant_service.send_text_message",
                send_mock,
            ),
        ):
            asyncio.run(
                process_financial_audio_message(
                    "5515999999999",
                    "wamid.large-audio",
                    "media-id",
                    "audio/ogg",
                )
            )

        process_mock.assert_not_awaited()
        self.assertEqual(
            send_mock.await_args_list[-1],
            call("5515999999999", audio_too_large_response()),
        )

    def test_processed_audio_is_not_downloaded_or_transcribed_again(self) -> None:
        send_mock = AsyncMock(return_value=True)
        download_mock = AsyncMock(return_value=self.media)
        transcribe_mock = AsyncMock(return_value="gastei 80 em diesel")

        with (
            patch(
                "backend.services.financial_assistant_service._message_already_processed",
                return_value=True,
            ),
            patch(
                "backend.services.financial_assistant_service.download_whatsapp_media",
                download_mock,
            ),
            patch(
                "backend.services.financial_assistant_service.transcribe_audio",
                transcribe_mock,
            ),
            patch(
                "backend.services.financial_assistant_service.send_text_message",
                send_mock,
            ),
        ):
            asyncio.run(
                process_financial_audio_message(
                    "5515999999999",
                    "wamid.duplicate",
                    "media-id",
                    "audio/ogg",
                )
            )

        download_mock.assert_not_awaited()
        transcribe_mock.assert_not_awaited()
        send_mock.assert_not_awaited()

    def _audio_patches(
        self,
        *,
        send_mock: AsyncMock,
        process_mock: AsyncMock,
        transcription: str = "",
        transcription_error: Exception | None = None,
    ):
        transcribe_result = AsyncMock(
            return_value=transcription,
            side_effect=transcription_error,
        )
        return _PatchGroup(
            patch(
                "backend.services.financial_assistant_service._message_already_processed",
                return_value=False,
            ),
            patch(
                "backend.services.financial_assistant_service.download_whatsapp_media",
                AsyncMock(return_value=self.media),
            ),
            patch(
                "backend.services.financial_assistant_service.transcribe_audio",
                transcribe_result,
            ),
            patch(
                "backend.services.financial_assistant_service.process_financial_message",
                process_mock,
            ),
            patch(
                "backend.services.financial_assistant_service.send_text_message",
                send_mock,
            ),
        )


class _PatchGroup:
    def __init__(self, *patchers) -> None:
        self.patchers = patchers

    def __enter__(self):
        return tuple(patcher.start() for patcher in self.patchers)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()


if __name__ == "__main__":
    unittest.main()
