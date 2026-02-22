import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import model_manager


class ModelManagerTests(unittest.TestCase):
    def test_resolve_model_dir_windows_appdata(self):
        with patch("platform.system", return_value="Windows"):
            with patch.dict(os.environ, {"APPDATA": r"C:\Users\alice\AppData\Roaming"}, clear=False):
                path = model_manager.resolve_model_dir()
        self.assertEqual(str(path).replace("/", "\\"), r"C:\Users\alice\AppData\Roaming\Fonte\models")

    def test_resolve_model_dir_linux(self):
        with patch("platform.system", return_value="Linux"):
            with patch("pathlib.Path.home", return_value=Path("/home/alice")):
                path = model_manager.resolve_model_dir()
        self.assertEqual(path, Path("/home/alice/.local/share/fonte/models"))

    def test_verify_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "m.gguf"
            payload = b"hello-offline-model"
            file_path.write_bytes(payload)
            sha = hashlib.sha256(payload).hexdigest()
            self.assertTrue(model_manager.verify_checksum(file_path, sha))
            self.assertFalse(model_manager.verify_checksum(file_path, "0" * 64))

    def test_check_installed_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "missing.gguf"
            self.assertFalse(model_manager.check_installed(file_path))


if __name__ == "__main__":
    unittest.main()
