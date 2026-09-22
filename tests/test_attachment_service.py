import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.services.attachment_service import (
    AttachmentStorageError,
    delete_stored_file,
    store_attachment_file,
    validate_attachment,
)


class AttachmentServiceTestCase(unittest.TestCase):
    def test_pdf_jpg_jpeg_and_png_are_stored_outside_database(self) -> None:
        samples = (
            ("arquivo.pdf", "application/pdf", b"%PDF-1.7 safe"),
            ("foto.jpg", "image/jpeg", b"\xff\xd8\xffsafe"),
            ("foto.jpeg", "image/jpeg", b"\xff\xd8\xffsafe"),
            ("foto.png", "image/png", b"\x89PNG\r\n\x1a\nsafe"),
        )
        with TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {"ATTACHMENT_STORAGE_DIR": temporary_directory},
                clear=False,
            ):
                for filename, mime_type, content in samples:
                    with self.subTest(filename=filename):
                        validated = validate_attachment(
                            content,
                            filename=filename,
                            mime_type=mime_type,
                        )
                        stored = store_attachment_file(validated, user_id=7)
                        path = Path(temporary_directory) / stored.storage_key
                        self.assertTrue(path.is_file())
                        self.assertEqual(path.read_bytes(), content)
                        self.assertIn("users/7/", stored.storage_key)
                        delete_stored_file(stored.storage_key)
                        self.assertFalse(path.exists())

    def test_invalid_signature_is_rejected(self) -> None:
        with self.assertRaises(AttachmentStorageError):
            validate_attachment(
                b"not-an-image",
                filename="comprovante.png",
                mime_type="image/png",
            )

    def test_original_filename_does_not_control_storage_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ,
                {"ATTACHMENT_STORAGE_DIR": temporary_directory},
                clear=False,
            ):
                validated = validate_attachment(
                    b"\x89PNG\r\n\x1a\nsafe",
                    filename="../../comprovante.png",
                    mime_type="image/png",
                )
                stored = store_attachment_file(validated, user_id=9)

        self.assertEqual(stored.original_filename, "comprovante.png")
        self.assertNotIn("..", stored.storage_key)


if __name__ == "__main__":
    unittest.main()
