import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from backend.services.ai_financial_service import GROQ_BASE_URL
from backend.services.audio_transcription_service import (
    DEFAULT_TRANSCRIPTION_MODEL,
    TRANSCRIPTION_TIMEOUT_SECONDS,
    AudioTranscriptionError,
    transcribe_audio,
)


class AudioTranscriptionServiceTestCase(unittest.TestCase):
    def test_transcribes_portuguese_audio_with_groq(self) -> None:
        client = Mock()
        client.close = AsyncMock()
        client.audio.transcriptions.create = AsyncMock(
            return_value=SimpleNamespace(
                text="  gastei oitenta conto de diesel hoje  "
            )
        )

        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "test-groq-key",
                "GROQ_TRANSCRIPTION_MODEL": DEFAULT_TRANSCRIPTION_MODEL,
            },
            clear=True,
        ):
            with patch(
                "backend.services.audio_transcription_service.AsyncOpenAI",
                return_value=client,
            ) as openai_client:
                text = asyncio.run(
                    transcribe_audio(
                        b"audio-bytes",
                        filename="audio.ogg",
                        mime_type="audio/ogg",
                    )
                )

        self.assertEqual(text, "gastei oitenta conto de diesel hoje")
        openai_client.assert_called_once_with(
            api_key="test-groq-key",
            base_url=GROQ_BASE_URL,
            timeout=TRANSCRIPTION_TIMEOUT_SECONDS,
            max_retries=1,
        )
        client.audio.transcriptions.create.assert_awaited_once_with(
            file=("audio.ogg", b"audio-bytes", "audio/ogg"),
            model=DEFAULT_TRANSCRIPTION_MODEL,
            language="pt",
            temperature=0,
            response_format="json",
        )
        client.close.assert_awaited_once_with()

    def test_missing_groq_key_raises_safe_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AudioTranscriptionError):
                asyncio.run(
                    transcribe_audio(
                        b"audio-bytes",
                        filename="audio.ogg",
                        mime_type="audio/ogg",
                    )
                )

    def test_provider_failure_is_wrapped(self) -> None:
        client = Mock()
        client.close = AsyncMock()
        client.audio.transcriptions.create = AsyncMock(
            side_effect=RuntimeError("provider unavailable")
        )

        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": "test-groq-key"},
            clear=True,
        ):
            with patch(
                "backend.services.audio_transcription_service.AsyncOpenAI",
                return_value=client,
            ):
                with self.assertRaises(AudioTranscriptionError):
                    asyncio.run(
                        transcribe_audio(
                            b"audio-bytes",
                            filename="audio.ogg",
                            mime_type="audio/ogg",
                        )
                    )


if __name__ == "__main__":
    unittest.main()
