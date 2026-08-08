import json
import tempfile
import unittest
from pathlib import Path

import photo_organizer_en as organizer

from photo_organizer_en import (
    ACTION_COPY,
    ACTION_MOVE,
    BUILTIN_PRESETS,
    exceeds_safety_threshold,
    get_app_directory,
    move_missing_files,
    parse_extensions,
    perform_file_operations,
    scan_files,
    undo_move,
)


class PhotoOrganizerV2Tests(unittest.TestCase):
    def test_safety_threshold_is_strictly_over_eighty_percent(self):
        self.assertFalse(exceeds_safety_threshold(8, 10))
        self.assertTrue(exceeds_safety_threshold(9, 10))
        self.assertFalse(exceeds_safety_threshold(0, 0))

    def test_builtin_camera_presets(self):
        self.assertEqual(BUILTIN_PRESETS["Sony · JPG → ARW"]["target_extensions"], ".ARW")
        self.assertEqual(BUILTIN_PRESETS["Canon · JPG → CR3"]["target_extensions"], ".CR3")
        self.assertEqual(BUILTIN_PRESETS["Nikon · JPG → NEF"]["target_extensions"], ".NEF")

    def test_xmp_is_off_by_default_in_builtin_presets(self):
        self.assertTrue(all(not preset["include_xmp"] for preset in BUILTIN_PRESETS.values()))

    def test_launcher_directory_argument(self):
        with tempfile.TemporaryDirectory() as temp:
            result = get_app_directory(["app.pyw", "--app-dir", temp])
            self.assertEqual(result, Path(temp).resolve())

    def test_language_switch_argument_path(self):
        with tempfile.TemporaryDirectory() as temp:
            result = organizer.get_argument_path(
                "--other-language-script",
                ["app.pyw", "--other-language-script", temp],
            )
            self.assertEqual(result, Path(temp).resolve())

    def test_frozen_language_restart_resets_pyinstaller_environment(self):
        environment = organizer.get_restart_environment(True)
        self.assertEqual(environment["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_language_switch_state_carries_settings_into_english(self):
        with tempfile.TemporaryDirectory() as temp:
            original_state_path = organizer.LANGUAGE_SWITCH_STATE
            state_path = Path(temp) / "language_switch_state.json"
            organizer.LANGUAGE_SWITCH_STATE = state_path
            try:
                state_path.write_text(
                    json.dumps(
                        {
                            "target_language": "en",
                            "reference_folder": "C:/photos",
                            "target_folder": "C:/photos",
                            "quarantine_folder": "D:/holding",
                            "same_folder": True,
                            "reference_extensions": ".ARW",
                            "target_extensions": ".JPG,.JPEG",
                            "recursive": True,
                            "include_xmp": False,
                            "mode_index": 1,
                            "operation_index": 1,
                        }
                    ),
                    encoding="utf-8",
                )
                result = organizer.apply_language_switch_state({}, "en")
                self.assertEqual(result["mode"], organizer.MODE_RAW_TO_JPG)
                self.assertEqual(result["operation"], organizer.ACTION_COPY)
                self.assertEqual(result["reference_extensions"], ".ARW")
                self.assertFalse(result["include_xmp"])
                self.assertFalse(state_path.exists())
            finally:
                organizer.LANGUAGE_SWITCH_STATE = original_state_path

    def test_parse_extensions(self):
        self.assertEqual(
            parse_extensions("ARW, .CR2，nef;ARW"),
            (".arw", ".cr2", ".nef"),
        )

    def test_jpg_reference_finds_raw_to_move(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "keep.ARW").write_bytes(b"raw")
            (folder / "keep.jpg").write_bytes(b"jpg")
            (folder / "move.ARW").write_bytes(b"raw")
            result = scan_files(folder, folder, (".jpg", ".jpeg"), (".arw",))
            self.assertEqual(result.target_count, 2)
            self.assertEqual(result.keep_count, 1)
            self.assertEqual(result.move_count, 1)

    def test_raw_reference_finds_jpg_to_move(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "keep.ARW").write_bytes(b"raw")
            (folder / "keep.JPG").write_bytes(b"jpg")
            (folder / "move.JPG").write_bytes(b"jpg")
            result = scan_files(folder, folder, (".arw",), (".jpg", ".jpeg"))
            self.assertEqual(result.target_count, 2)
            self.assertEqual(result.keep_count, 1)
            self.assertEqual(result.move_count, 1)

    def test_custom_formats(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "one.TIF").write_bytes(b"tif")
            (folder / "one.PNG").write_bytes(b"png")
            (folder / "two.PNG").write_bytes(b"png")
            result = scan_files(folder, folder, (".tif",), (".png",))
            self.assertEqual(result.reference_count, 1)
            self.assertEqual(result.keep_count, 1)
            self.assertEqual(result.move_count, 1)

    def test_recursive_matching_respects_relative_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "day1").mkdir()
            (folder / "day2").mkdir()
            (folder / "day1" / "same.ARW").write_bytes(b"raw1")
            (folder / "day2" / "same.ARW").write_bytes(b"raw2")
            (folder / "day1" / "same.JPG").write_bytes(b"jpg")
            result = scan_files(
                folder, folder, (".jpg",), (".arw",), recursive=True
            )
            self.assertEqual(result.keep_count, 1)
            self.assertEqual(result.move_count, 1)

    def test_move_goes_directly_to_selected_folder_and_undoes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            target_root = base / "photos"
            quarantine = base / "quarantine"
            (target_root / "trip").mkdir(parents=True)
            target = target_root / "trip" / "DSC1000.ARW"
            target.write_bytes(b"raw")
            result = scan_files(
                target_root,
                target_root,
                (".jpg",),
                (".arw",),
                recursive=True,
            )

            log_path, moved, errors = move_missing_files(
                result.items, target_root, quarantine, base / "logs"
            )
            destination = quarantine / "trip" / "DSC1000.ARW"
            self.assertEqual(moved, 1)
            self.assertEqual(errors, [])
            self.assertTrue(destination.exists())
            self.assertEqual(destination.parent, quarantine / "trip")
            self.assertFalse(log_path.is_relative_to(quarantine))
            log = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(Path(log["moves"][0]["destination"]), destination)

            restored, undo_errors = undo_move(log_path)
            self.assertEqual(restored, 1)
            self.assertEqual(undo_errors, [])
            self.assertTrue(target.exists())

    def test_quarantine_inside_scan_root_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            quarantine = folder / "temporary"
            quarantine.mkdir()
            (folder / "new.ARW").write_bytes(b"raw")
            (quarantine / "old.ARW").write_bytes(b"raw")
            result = scan_files(
                folder,
                folder,
                (".jpg",),
                (".arw",),
                recursive=True,
                excluded_roots=(quarantine,),
            )
            self.assertEqual(result.target_count, 1)
            self.assertEqual(Path(result.items[0].target_path).name, "new.ARW")

    def test_move_never_overwrites_existing_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            target_root = base / "photos"
            quarantine = base / "quarantine"
            target_root.mkdir()
            quarantine.mkdir()
            source = target_root / "same.JPG"
            destination = quarantine / "same.JPG"
            source.write_bytes(b"source")
            destination.write_bytes(b"existing")
            result = scan_files(target_root, target_root, (".arw",), (".jpg",))
            _log_path, moved, errors = move_missing_files(
                result.items, target_root, quarantine, base / "logs"
            )
            self.assertEqual(moved, 0)
            self.assertEqual(len(errors), 1)
            self.assertEqual(source.read_bytes(), b"source")
            self.assertEqual(destination.read_bytes(), b"existing")

    def test_xmp_moves_with_target_and_is_undone(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            target_root = base / "photos"
            quarantine = base / "quarantine"
            target_root.mkdir()
            raw = target_root / "DSC3000.ARW"
            xmp = target_root / "DSC3000.XMP"
            raw.write_bytes(b"raw")
            xmp.write_bytes(b"xmp")
            result = scan_files(target_root, target_root, (".jpg",), (".arw",))

            log_path, primary, sidecars, errors = perform_file_operations(
                result.items,
                target_root,
                quarantine,
                ACTION_MOVE,
                True,
                base / "logs",
            )
            self.assertEqual((primary, sidecars, errors), (1, 1, []))
            self.assertTrue((quarantine / raw.name).exists())
            self.assertTrue((quarantine / xmp.name).exists())

            restored, undo_errors = undo_move(log_path)
            self.assertEqual(restored, 2)
            self.assertEqual(undo_errors, [])
            self.assertTrue(raw.exists())
            self.assertTrue(xmp.exists())

    def test_copy_undo_removes_only_created_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            target_root = base / "photos"
            quarantine = base / "copies"
            target_root.mkdir()
            source = target_root / "DSC4000.JPG"
            source.write_bytes(b"jpg")
            result = scan_files(target_root, target_root, (".arw",), (".jpg",))

            log_path, primary, sidecars, errors = perform_file_operations(
                result.items,
                target_root,
                quarantine,
                ACTION_COPY,
                False,
                base / "logs",
            )
            destination = quarantine / source.name
            self.assertEqual((primary, sidecars, errors), (1, 0, []))
            self.assertTrue(source.exists())
            self.assertTrue(destination.exists())

            restored, undo_errors = undo_move(log_path)
            self.assertEqual(restored, 1)
            self.assertEqual(undo_errors, [])
            self.assertTrue(source.exists())
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
