import base64
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import attachments
from attachments import AttachmentStore


def data_url(mime_type, payload):
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class CacheFixture:
    def __init__(self, root):
        self.root = Path(root)
        self.counter = 0

    def image(self, payload, ext):
        return self._write(payload, f"image{ext}")

    def document(self, payload, filename):
        return self._write(payload, Path(filename).name)

    def _write(self, payload, filename):
        self.counter += 1
        path = self.root / f"{self.counter}-{filename}"
        path.write_bytes(payload)
        return str(path)


class AttachmentStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cache = CacheFixture(self.temporary.name)
        self.store = AttachmentStore(cache_image=self.cache.image, cache_document=self.cache.document)
        self.owner = object()

    def tearDown(self):
        self.store.clear()
        self.temporary.cleanup()

    def test_image_is_validated_cached_and_consumed_once(self):
        png = b"\x89PNG\r\n\x1a\n" + b"safe-image-bytes"
        result = self.store.stage_image(self.owner, {
            "session_id": "browser-session",
            "data_url": data_url("image/png", png),
            "filename": "photo.png",
        })

        staged = self.store.take(self.owner, "browser-session")
        self.assertTrue(result["attached"])
        self.assertEqual(staged[0].mime_type, "image/png")
        self.assertEqual(Path(staged[0].path).read_bytes(), png)
        self.assertEqual(self.store.take(self.owner, "browser-session"), [])

    def test_image_rejects_fake_bytes_and_mismatched_mime(self):
        with self.assertRaisesRegex(ValueError, "invalid image"):
            self.store.stage_image(self.owner, {
                "session_id": "browser-session",
                "data_url": data_url("image/png", b"not-an-image"),
            })
        jpeg = b"\xff\xd8\xff" + b"jpeg-bytes"
        with self.assertRaisesRegex(ValueError, "MIME type"):
            self.store.stage_image(self.owner, {
                "session_id": "browser-session",
                "data_url": data_url("image/png", jpeg),
            })

    def test_file_sanitizes_name_and_validates_document_structure(self):
        pdf = b"%PDF-1.7\nvalid-enough-for-staging"
        result = self.store.stage_file(self.owner, {
            "session_id": "browser-session",
            "data_url": data_url("application/pdf", pdf),
            "name": "../../quote.pdf",
        })

        staged = self.store.take(self.owner, "browser-session")
        self.assertEqual(result["name"], "quote.pdf")
        self.assertEqual(staged[0].mime_type, "application/pdf")
        with self.assertRaisesRegex(ValueError, "invalid PDF"):
            self.store.stage_file(self.owner, {
                "session_id": "browser-session",
                "data_url": data_url("application/pdf", b"not-a-pdf"),
                "name": "fake.pdf",
            })
        with self.assertRaisesRegex(ValueError, "unsupported file type"):
            self.store.stage_file(self.owner, {
                "session_id": "browser-session",
                "data_url": data_url("application/octet-stream", b"binary"),
                "name": "payload.exe",
            })

    def test_office_documents_require_the_expected_archive_tree(self):
        valid_docx = io.BytesIO()
        with zipfile.ZipFile(valid_docx, "w") as archive:
            archive.writestr("[Content_Types].xml", "types")
            archive.writestr("word/document.xml", "document")
        self.store.stage_file(self.owner, {
            "session_id": "browser-session",
            "data_url": data_url("application/octet-stream", valid_docx.getvalue()),
            "name": "brief.docx",
        })

        invalid_docx = io.BytesIO()
        with zipfile.ZipFile(invalid_docx, "w") as archive:
            archive.writestr("unrelated.txt", "not a document")
        with self.assertRaisesRegex(ValueError, "invalid DOCX"):
            self.store.stage_file(self.owner, {
                "session_id": "browser-session",
                "data_url": data_url("application/octet-stream", invalid_docx.getvalue()),
                "name": "fake.docx",
            })

    def test_pending_media_is_isolated_and_removed_when_its_owner_disconnects(self):
        second_owner = object()
        first_pdf = b"%PDF-1.7\nfirst"
        second_pdf = b"%PDF-1.7\nsecond"
        self.store.stage_file(self.owner, {
            "session_id": "shared-session",
            "data_url": data_url("application/pdf", first_pdf),
            "name": "first.pdf",
        })
        self.store.stage_file(second_owner, {
            "session_id": "shared-session",
            "data_url": data_url("application/pdf", second_pdf),
            "name": "second.pdf",
        })
        second_path = self.store.take(second_owner, "shared-session")[0].path
        first_path = next(Path(self.temporary.name).glob("*-first.pdf"))

        self.store.discard_owner(self.owner)

        self.assertFalse(first_path.exists())
        self.assertTrue(Path(second_path).exists())

    def test_limits_are_checked_before_a_second_cache_write(self):
        pdf = b"%PDF-1.7\nsmall"
        with mock.patch.object(attachments, "MAX_SESSION_ATTACHMENTS", 1):
            self.store.stage_file(self.owner, {
                "session_id": "browser-session",
                "data_url": data_url("application/pdf", pdf),
                "name": "first.pdf",
            })
            with self.assertRaisesRegex(ValueError, "attachment-count-limit"):
                self.store.stage_file(self.owner, {
                    "session_id": "browser-session",
                    "data_url": data_url("application/pdf", pdf),
                    "name": "second.pdf",
                })
        self.assertEqual(self.cache.counter, 1)


if __name__ == "__main__":
    unittest.main()
