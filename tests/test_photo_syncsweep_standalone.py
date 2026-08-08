import tempfile
import unittest
from pathlib import Path

import photo_syncsweep_standalone as standalone


class StandaloneLauncherTests(unittest.TestCase):
    def test_command_line_language_has_priority(self):
        self.assertEqual(
            standalone.selected_language(["PhotoSyncSweep.exe", "--language", "zh"]),
            "zh",
        )

    def test_saved_language_is_loaded(self):
        with tempfile.TemporaryDirectory() as temp:
            original_path = standalone.LANGUAGE_FILE
            standalone.LANGUAGE_FILE = Path(temp) / "language.txt"
            try:
                standalone.LANGUAGE_FILE.write_text("zh", encoding="utf-8")
                self.assertEqual(standalone.selected_language(["PhotoSyncSweep.exe"]), "zh")
            finally:
                standalone.LANGUAGE_FILE = original_path

if __name__ == "__main__":
    unittest.main()
