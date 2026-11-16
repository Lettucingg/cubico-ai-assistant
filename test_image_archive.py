"""Pruebas del archivo privado sin acceso a red ni credenciales."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.services import image_archive as archive

PNG = b"\x89PNG\r\n\x1a\n" + b"fixture-image-bytes"
JPEG = b"\xff\xd8\xff" + b"fixture-image-bytes"


class ImageArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "private"

    def test_persists_formats_and_returns_original_bytes(self):
        formats = [(PNG, "image/png"), (JPEG, "image/jpeg"),
                   (b"GIF89aimage", "image/gif"), (b"RIFFxxxxWEBPimage", "image/webp")]
        for index, (data, mime) in enumerate(formats):
            with self.subTest(mime=mime):
                archive.save_image(str(index), data, self.directory)
                self.assertEqual(archive.read_image(str(index), self.directory), data)
                self.assertEqual(archive.image_mime(data), mime)

    def test_missing_image_is_not_an_error(self):
        self.assertIsNone(archive.read_image("missing", self.directory))
        self.assertFalse(self.directory.exists())

    def test_private_permissions(self):
        archive.save_image("private", PNG, self.directory)
        if os.name == "posix":
            self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
            target = next(self.directory.glob("*.image"))
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_media_id_cannot_select_arbitrary_path(self):
        archive.save_image("../../outside", PNG, self.directory)
        files = list(self.directory.iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].parent, self.directory)
        self.assertNotIn("outside", files[0].name)

    def test_invalid_payloads_do_not_create_files(self):
        for data in (b"", b"<html>not an image</html>", PNG + bytes(archive.MAX_IMAGE_BYTES)):
            with self.subTest(length=len(data)):
                with self.assertRaises(ValueError):
                    archive.save_image("invalid", data, self.directory)
        self.assertFalse(self.directory.exists())

    def test_same_identifier_is_idempotent_and_preserves_original(self):
        archive.save_image("same", PNG, self.directory)
        target = next(self.directory.glob("*.image"))
        timestamp = target.stat().st_mtime_ns
        archive.save_image("same", PNG, self.directory)
        self.assertEqual(target.stat().st_mtime_ns, timestamp)
        with self.assertRaises(ValueError):
            archive.save_image("same", JPEG, self.directory)
        self.assertEqual(archive.read_image("same", self.directory), PNG)

    def test_failed_atomic_replace_leaves_no_partial_image(self):
        with patch.object(archive.os, "replace", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                archive.save_image("failure", PNG, self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_symlink_cannot_read_outside_file(self):
        if os.name != "posix":
            self.skipTest("POSIX symlink test")
        self.directory.mkdir()
        outside = Path(self.temp.name) / "outside"
        outside.write_bytes(PNG)
        target = archive._target("linked", self.directory)
        target.symlink_to(outside)
        with self.assertRaises(ValueError):
            archive.read_image("linked", self.directory)
        with self.assertRaises(ValueError):
            archive.save_image("linked", PNG, self.directory)

    def test_public_directory_is_rejected(self):
        public = Path(archive.__file__).resolve().parents[2] / "app" / "static" / "private-test"
        with self.assertRaises(ValueError):
            archive.save_image("public", PNG, public)

    def test_invalid_identifiers_are_rejected(self):
        for media_id in ("", None, "a" * 257):
            with self.assertRaises(ValueError):
                archive.read_image(media_id, self.directory)


if __name__ == "__main__":
    unittest.main()
