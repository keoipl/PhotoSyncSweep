from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import ctypes
import webbrowser
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from photo_organizer_en import (
    FluentCheckbutton,
    RoundedButton,
    RoundedCard,
    RoundedEntry,
    RoundedSelect,
)


APP_NAME = "Photo SyncSweep 照片联动清理助手"
APP_VERSION = "1.0.0"
AUTHOR_URL = "https://github.com/keoipl"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "PhotoRawSync"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_DIR = CONFIG_DIR / "logs"
LANGUAGE_SWITCH_STATE = CONFIG_DIR / "language_switch_state.json"

MODE_JPG_TO_RAW = "根据 JPG 整理 RAW"
MODE_RAW_TO_JPG = "根据 RAW 整理 JPG"
MODE_CUSTOM = "自定义格式"
ACTION_MOVE = "移动到暂存文件夹"
ACTION_COPY = "复制到暂存文件夹"
ACTION_RECYCLE = "移入 Windows 回收站"
CUSTOM_PRESET_LABEL = "自定义设置"
MODE_SETTINGS = {
    MODE_JPG_TO_RAW: {
        "reference_name": "JPG",
        "target_name": "RAW",
        "reference_extensions": ".JPG,.JPEG",
        "target_extensions": ".ARW",
        "note": "适合先在 JPG 中筛选照片：被删掉 JPG 后，缺少同名 JPG 的 RAW 会进入待移动清单。",
    },
    MODE_RAW_TO_JPG: {
        "reference_name": "RAW",
        "target_name": "JPG",
        "reference_extensions": ".ARW",
        "target_extensions": ".JPG,.JPEG",
        "note": "适合以 RAW 为保留标准：缺少同名 RAW 的 JPG/JPEG 会进入待移动清单。",
    },
    MODE_CUSTOM: {
        "reference_name": "依据格式",
        "target_name": "待整理格式",
        "reference_extensions": "",
        "target_extensions": "",
        "note": "依据格式是保留标准；待整理格式文件如果找不到同名依据文件，就会进入待移动清单。",
    },
}

BUILTIN_PRESETS = {
    "Sony：JPG → ARW": {
        "mode": MODE_JPG_TO_RAW,
        "reference_extensions": ".JPG,.JPEG",
        "target_extensions": ".ARW",
        "operation": ACTION_MOVE,
        "include_xmp": False,
    },
    "Canon：JPG → CR3": {
        "mode": MODE_JPG_TO_RAW,
        "reference_extensions": ".JPG,.JPEG",
        "target_extensions": ".CR3",
        "operation": ACTION_MOVE,
        "include_xmp": False,
    },
    "Nikon：JPG → NEF": {
        "mode": MODE_JPG_TO_RAW,
        "reference_extensions": ".JPG,.JPEG",
        "target_extensions": ".NEF",
        "operation": ACTION_MOVE,
        "include_xmp": False,
    },
}


def exceeds_safety_threshold(selected_count: int, total_count: int) -> bool:
    return total_count > 0 and selected_count / total_count > 0.8


def get_app_directory(argv: list[str] | None = None) -> Path:
    """Return the launcher EXE directory, or the script directory as fallback."""
    arguments = list(sys.argv if argv is None else argv)
    try:
        index = arguments.index("--app-dir")
        if index + 1 < len(arguments) and arguments[index + 1].strip():
            return Path(arguments[index + 1]).resolve()
    except ValueError:
        pass
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_icon_path(argv: list[str] | None = None) -> Path | None:
    arguments = list(sys.argv if argv is None else argv)
    try:
        index = arguments.index("--icon")
        if index + 1 < len(arguments):
            candidate = Path(arguments[index + 1]).resolve()
            return candidate if candidate.is_file() else None
    except ValueError:
        pass
    return None


def get_argument_path(flag: str, argv: list[str] | None = None) -> Path | None:
    arguments = list(sys.argv if argv is None else argv)
    try:
        index = arguments.index(flag)
        if index + 1 < len(arguments) and arguments[index + 1].strip():
            return Path(arguments[index + 1]).resolve()
    except ValueError:
        pass
    return None


def get_restart_environment(frozen_app: bool) -> dict[str, str]:
    environment = os.environ.copy()
    if frozen_app:
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return environment


def apply_language_switch_state(config: dict, language: str) -> dict:
    try:
        payload = json.loads(LANGUAGE_SWITCH_STATE.read_text(encoding="utf-8"))
        if payload.get("target_language") != language:
            return config
        for key in (
            "reference_folder",
            "target_folder",
            "quarantine_folder",
            "same_folder",
            "reference_extensions",
            "target_extensions",
            "recursive",
            "include_xmp",
        ):
            if key in payload:
                config[key] = payload[key]
        modes = (MODE_JPG_TO_RAW, MODE_RAW_TO_JPG, MODE_CUSTOM)
        actions = (ACTION_MOVE, ACTION_COPY, ACTION_RECYCLE)
        config["mode"] = modes[int(payload.get("mode_index", 0))]
        config["operation"] = actions[int(payload.get("operation_index", 0))]
        config["preset_name"] = CUSTOM_PRESET_LABEL
        LANGUAGE_SWITCH_STATE.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError, IndexError, json.JSONDecodeError):
        pass
    return config


@dataclass
class ScanItem:
    target_path: str
    relative_path: str
    has_reference: bool

    @property
    def action(self) -> str:
        return "保留" if self.has_reference else "待移动"


@dataclass
class ScanResult:
    items: list[ScanItem]
    target_count: int
    reference_count: int

    @property
    def keep_count(self) -> int:
        return sum(item.has_reference for item in self.items)

    @property
    def move_count(self) -> int:
        return self.target_count - self.keep_count


def parse_extensions(value: str) -> tuple[str, ...]:
    """Normalize a comma/semicolon separated extension list."""
    values: list[str] = []
    for part in value.replace("，", ",").replace(";", ",").split(","):
        extension = part.strip().lower()
        if not extension:
            continue
        if not extension.startswith("."):
            extension = f".{extension}"
        if extension not in values:
            values.append(extension)
    return tuple(values)


def _is_within(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def _iter_files(
    folder: Path, recursive: bool, excluded_roots: Iterable[Path] = ()
) -> Iterable[Path]:
    excludes = [root.resolve() for root in excluded_roots]
    iterator = folder.rglob("*") if recursive else folder.iterdir()
    for path in iterator:
        if not path.is_file():
            continue
        if any(_is_within(path, root) for root in excludes):
            continue
        yield path


def scan_files(
    reference_root: Path,
    target_root: Path,
    reference_extensions: tuple[str, ...],
    target_extensions: tuple[str, ...],
    recursive: bool = False,
    excluded_roots: Iterable[Path] = (),
) -> ScanResult:
    """Find target files that do not have a same-stem reference file.

    Matching is case-insensitive and respects the relative subfolder. The
    excluded roots are useful when the temporary folder sits inside a scanned
    photo folder.
    """
    reference_root = reference_root.resolve()
    target_root = target_root.resolve()
    if not reference_root.is_dir():
        raise ValueError("依据文件夹不存在或无法访问。")
    if not target_root.is_dir():
        raise ValueError("待整理文件夹不存在或无法访问。")
    if not reference_extensions:
        raise ValueError("请至少填写一种依据格式。")
    if not target_extensions:
        raise ValueError("请至少填写一种待整理格式。")

    reference_keys: set[tuple[str, str]] = set()
    reference_count = 0
    for reference_path in _iter_files(reference_root, recursive, excluded_roots):
        if reference_path.suffix.lower() not in reference_extensions:
            continue
        relative_parent = (
            reference_path.relative_to(reference_root).parent.as_posix().casefold()
        )
        reference_keys.add((relative_parent, reference_path.stem.casefold()))
        reference_count += 1

    target_paths = sorted(
        (
            path
            for path in _iter_files(target_root, recursive, excluded_roots)
            if path.suffix.lower() in target_extensions
        ),
        key=lambda path: path.as_posix().casefold(),
    )

    items: list[ScanItem] = []
    for target_path in target_paths:
        relative = target_path.relative_to(target_root)
        key = (relative.parent.as_posix().casefold(), target_path.stem.casefold())
        items.append(
            ScanItem(
                target_path=str(target_path),
                relative_path=str(relative),
                has_reference=key in reference_keys,
            )
        )
    return ScanResult(
        items=items,
        target_count=len(items),
        reference_count=reference_count,
    )


def scan_photos(
    jpg_root: Path,
    raw_root: Path,
    raw_extensions: tuple[str, ...],
    recursive: bool = False,
) -> ScanResult:
    """Compatibility wrapper for JPG -> RAW matching."""
    return scan_files(
        jpg_root,
        raw_root,
        (".jpg", ".jpeg"),
        raw_extensions,
        recursive,
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _new_log_path(log_dir: Path = LOG_DIR) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = log_dir / f"操作记录_{stamp}.json"
    index = 2
    while candidate.exists():
        candidate = log_dir / f"操作记录_{stamp}_{index}.json"
        index += 1
    return candidate


def _find_xmp_sidecar(source: Path, cache: dict[Path, dict[str, Path]]) -> Path | None:
    folder = source.parent.resolve()
    if folder not in cache:
        cache[folder] = {
            path.stem.casefold(): path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.casefold() == ".xmp"
        }
    return cache[folder].get(source.stem.casefold())


def _send_to_recycle_bin(path: Path) -> None:
    if os.name != "nt":
        raise OSError("Windows 回收站模式只支持 Windows。")

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x0040
    FOF_WANTNUKEWARNING = 0x4000
    operation = SHFILEOPSTRUCTW()
    operation.wFunc = FO_DELETE
    operation.pFrom = str(path.resolve()) + "\0\0"
    # Keep Windows' own warning if a file cannot actually enter the Recycle Bin.
    operation.fFlags = FOF_ALLOWUNDO | FOF_WANTNUKEWARNING
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(f"移入回收站失败，Windows 错误代码：{result}")


def perform_file_operations(
    items: list[ScanItem],
    target_root: Path,
    quarantine_root: Path | None,
    operation: str = ACTION_MOVE,
    include_xmp: bool = False,
    log_dir: Path = LOG_DIR,
) -> tuple[Path | None, int, int, list[str]]:
    pending = [item for item in items if not item.has_reference]
    if not pending:
        return None, 0, 0, []
    if operation not in (ACTION_MOVE, ACTION_COPY, ACTION_RECYCLE):
        raise ValueError("未知的文件处理方式。")

    target_root = target_root.resolve()
    if operation != ACTION_RECYCLE:
        if quarantine_root is None:
            raise ValueError("请选择暂存文件夹。")
        quarantine_root = quarantine_root.resolve()
        if target_root == quarantine_root:
            raise ValueError("待整理文件夹和暂存文件夹不能相同。")
        quarantine_root.mkdir(parents=True, exist_ok=True)

    log_path = _new_log_path(log_dir)
    log: dict = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target_root": str(target_root),
        "quarantine_root": str(quarantine_root or ""),
        "operation": operation,
        "include_xmp": include_xmp,
        "completed": False,
        "undone": False,
        "moves": [],
    }
    _write_json(log_path, log)

    primary_success = 0
    xmp_success = 0
    errors: list[str] = []
    xmp_cache: dict[Path, dict[str, Path]] = {}
    processed_sidecars: set[Path] = set()
    selected_sources = {Path(item.target_path).resolve() for item in pending}

    def process_one(source: Path, relative: Path, kind: str) -> bool:
        destination = (
            None
            if operation == ACTION_RECYCLE
            else quarantine_root / relative  # type: ignore[operator]
        )
        record = {
            "source": str(source),
            "destination": str(destination or ""),
            "kind": kind,
            "operation": operation,
        }
        try:
            if not _is_within(source, target_root):
                raise ValueError("文件不在所选待整理文件夹内")
            if not source.exists():
                raise FileNotFoundError("源文件已不存在")
            if quarantine_root is not None and _is_within(source, quarantine_root):
                raise ValueError("文件已经位于暂存文件夹内")

            if operation == ACTION_RECYCLE:
                _send_to_recycle_bin(source)
                record["status"] = "recycled"
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
                if destination.exists():  # type: ignore[union-attr]
                    raise FileExistsError("暂存位置已有同名文件，为避免覆盖已跳过")
                if operation == ACTION_MOVE:
                    shutil.move(str(source), str(destination))
                    record["status"] = "moved"
                else:
                    shutil.copy2(str(source), str(destination))
                    stat = destination.stat()  # type: ignore[union-attr]
                    record["status"] = "copied"
                    record["size"] = stat.st_size
                    record["mtime_ns"] = stat.st_mtime_ns
            log["moves"].append(record)
            return True
        except Exception as exc:
            errors.append(f"{source.name}: {exc}")
            record["status"] = "error"
            record["error"] = str(exc)
            log["moves"].append(record)
            return False
        finally:
            _write_json(log_path, log)

    for item in pending:
        source = Path(item.target_path).resolve()
        sidecar = None
        if include_xmp:
            sidecar = _find_xmp_sidecar(source, xmp_cache)
        if not process_one(source, Path(item.relative_path), "target"):
            continue
        primary_success += 1

        if sidecar is None:
            continue
        sidecar = sidecar.resolve()
        if sidecar in processed_sidecars or sidecar in selected_sources:
            continue
        processed_sidecars.add(sidecar)
        sidecar_relative = Path(item.relative_path).parent / sidecar.name
        if process_one(sidecar, sidecar_relative, "xmp"):
            xmp_success += 1

    log["completed"] = True
    log["completed_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(log_path, log)
    return log_path, primary_success, xmp_success, errors


def move_missing_files(
    items: list[ScanItem],
    target_root: Path,
    quarantine_root: Path,
    log_dir: Path = LOG_DIR,
) -> tuple[Path | None, int, list[str]]:
    log_path, moved, _xmp_count, errors = perform_file_operations(
        items,
        target_root,
        quarantine_root,
        ACTION_MOVE,
        False,
        log_dir,
    )
    return log_path, moved, errors


def move_missing_raws(
    items: list[ScanItem], raw_root: Path, quarantine_root: Path
) -> tuple[Path | None, int, list[str]]:
    """Compatibility wrapper for the original function name."""
    return move_missing_files(items, raw_root, quarantine_root)


def undo_move(log_path: Path) -> tuple[int, list[str]]:
    if not log_path.is_file():
        raise ValueError("找不到上一次操作记录。")
    log = json.loads(log_path.read_text(encoding="utf-8"))
    if log.get("undone"):
        raise ValueError("这次操作已经撤销过了。")
    if log.get("operation") == ACTION_RECYCLE or any(
        record.get("status") == "recycled" for record in log.get("moves", [])
    ):
        raise ValueError("回收站操作请打开 Windows 回收站手动恢复。")

    restored = 0
    errors: list[str] = []
    for record in reversed(log.get("moves", [])):
        if record.get("status") not in ("moved", "copied"):
            continue
        source = Path(record["source"])
        destination = Path(record["destination"])
        try:
            if not destination.exists():
                raise FileNotFoundError("暂存文件已不存在")
            if record.get("status") == "moved":
                if source.exists():
                    raise FileExistsError("原位置已有同名文件，为避免覆盖已跳过")
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
                record["status"] = "restored"
            else:
                if not source.exists():
                    raise FileNotFoundError("原文件已不存在，不能确认副本是否安全删除")
                destination_stat = destination.stat()
                source_stat = source.stat()
                if (
                    destination_stat.st_size != record.get("size")
                    or destination_stat.st_mtime_ns != record.get("mtime_ns")
                    or source_stat.st_size != destination_stat.st_size
                ):
                    raise ValueError("副本可能已被修改，为避免误删已跳过")
                destination.unlink()
                record["status"] = "copy_removed"
            restored += 1
        except Exception as exc:
            errors.append(f"{source.name}: {exc}")
            record["undo_error"] = str(exc)
        _write_json(log_path, log)

    log["undone"] = not errors
    log["undo_completed_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(log_path, log)
    return restored, errors


def load_config() -> dict:
    defaults = {
        "mode": MODE_JPG_TO_RAW,
        "reference_folder": "",
        "target_folder": "",
        "quarantine_folder": r"C:\照片\垃圾桶",
        "same_folder": True,
        "reference_extensions": ".JPG,.JPEG",
        "target_extensions": ".ARW",
        "recursive": False,
        "operation": ACTION_MOVE,
        "include_xmp": False,
        "config_version": 4,
        "preset_name": "Sony：JPG → ARW",
        "custom_presets": {},
        "last_log": "",
    }
    try:
        saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        # Migrate settings saved by version 1.
        if "reference_folder" not in saved and "jpg_folder" in saved:
            saved["reference_folder"] = saved.get("jpg_folder", "")
        if "target_folder" not in saved and "raw_folder" in saved:
            saved["target_folder"] = saved.get("raw_folder", "")
        if "target_extensions" not in saved and "raw_extensions" in saved:
            saved["target_extensions"] = saved.get("raw_extensions", ".ARW")
        if int(saved.get("config_version", 0) or 0) < 4:
            saved["include_xmp"] = False
            saved["config_version"] = 4
        defaults.update(saved)
    except (OSError, ValueError, TypeError):
        pass
    if defaults["mode"] not in MODE_SETTINGS:
        defaults["mode"] = MODE_JPG_TO_RAW
    if defaults["operation"] not in (ACTION_MOVE, ACTION_COPY, ACTION_RECYCLE):
        defaults["operation"] = ACTION_MOVE
    if not isinstance(defaults.get("custom_presets"), dict):
        defaults["custom_presets"] = {}
    return apply_language_switch_state(defaults, "zh")


def save_config(config: dict) -> None:
    _write_json(CONFIG_FILE, config)


def open_folder(path: Path) -> None:
    if not path.exists():
        raise ValueError("文件夹不存在。")
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


class PhotoOrganizerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        icon_path = get_icon_path()
        if icon_path:
            try:
                self.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.geometry("1160x850")
        self.minsize(980, 700)
        self.option_add("*Font", ("Microsoft YaHei UI", 10))

        config = load_config()
        self.mode_var = tk.StringVar(value=config["mode"])
        self.reference_var = tk.StringVar(value=config["reference_folder"])
        self.target_var = tk.StringVar(value=config["target_folder"])
        self.quarantine_var = tk.StringVar(value=config["quarantine_folder"])
        self.same_var = tk.BooleanVar(value=config["same_folder"])
        self.reference_ext_var = tk.StringVar(value=config["reference_extensions"])
        self.target_ext_var = tk.StringVar(value=config["target_extensions"])
        self.recursive_var = tk.BooleanVar(value=config["recursive"])
        self.operation_var = tk.StringVar(value=config["operation"])
        self.include_xmp_var = tk.BooleanVar(value=config["include_xmp"])
        self.custom_presets: dict[str, dict] = dict(config["custom_presets"])
        saved_preset = str(config.get("preset_name", CUSTOM_PRESET_LABEL))
        if saved_preset not in BUILTIN_PRESETS and saved_preset not in self.custom_presets:
            saved_preset = CUSTOM_PRESET_LABEL
        self.preset_var = tk.StringVar(value=saved_preset)
        self.last_log = str(config.get("last_log", ""))
        self.scan_result: ScanResult | None = None
        self.app_directory = get_app_directory()
        self.selected_paths: set[str] = set()
        self.item_by_iid: dict[str, ScanItem] = {}
        self._applying_preset = False

        self.reference_folder_label_var = tk.StringVar()
        self.target_folder_label_var = tk.StringVar()
        self.reference_ext_label_var = tk.StringVar()
        self.target_ext_label_var = tk.StringVar()
        self.same_text_var = tk.StringVar()
        self.mode_note_var = tk.StringVar()
        self.warning_var = tk.StringVar()
        self.quarantine_label_var = tk.StringVar(value="暂存文件夹")

        self._configure_style()
        self._build_ui()
        self._refresh_preset_values()
        self._update_mode_labels()
        self._update_operation_ui()
        self._toggle_same_folder()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._apply_windows11_effects)

    def _mode_info(self) -> dict[str, str]:
        return MODE_SETTINGS[self.mode_var.get()]

    def _switch_language(self, target_language: str) -> None:
        frozen_app = bool(getattr(sys, "frozen", False))
        other_script = get_argument_path("--other-language-script")
        if not frozen_app and (other_script is None or not other_script.is_file()):
            messagebox.showerror(
                "语言包不可用",
                "请从合并后的 EXE 启动程序，才能切换语言。",
                parent=self,
            )
            return
        try:
            modes = (MODE_JPG_TO_RAW, MODE_RAW_TO_JPG, MODE_CUSTOM)
            actions = (ACTION_MOVE, ACTION_COPY, ACTION_RECYCLE)
            payload = {
                "target_language": target_language,
                "reference_folder": self.reference_var.get().strip(),
                "target_folder": self.target_var.get().strip(),
                "quarantine_folder": self.quarantine_var.get().strip(),
                "same_folder": self.same_var.get(),
                "reference_extensions": self.reference_ext_var.get().strip(),
                "target_extensions": self.target_ext_var.get().strip(),
                "recursive": self.recursive_var.get(),
                "include_xmp": self.include_xmp_var.get(),
                "mode_index": modes.index(self.mode_var.get()),
                "operation_index": actions.index(self.operation_var.get()),
            }
            _write_json(LANGUAGE_SWITCH_STATE, payload)
            self._save_current_config()
            language_file = get_argument_path("--language-file") or (CONFIG_DIR / "language.txt")
            language_file.parent.mkdir(parents=True, exist_ok=True)
            language_file.write_text(target_language, encoding="utf-8")
            if frozen_app:
                arguments = [sys.executable, "--language", target_language]
                working_directory = str(Path(sys.executable).resolve().parent)
            else:
                arguments = [
                    sys.executable,
                    str(other_script),
                    "--app-dir",
                    str(self.app_directory),
                    "--other-language-script",
                    str(Path(__file__).resolve()),
                    "--language-file",
                    str(language_file),
                    "--language",
                    target_language,
                ]
                icon_path = get_icon_path()
                if icon_path:
                    arguments.extend(("--icon", str(icon_path)))
                working_directory = str(other_script.parent)
            subprocess.Popen(
                arguments,
                cwd=working_directory,
                close_fds=True,
                env=get_restart_environment(frozen_app),
            )
            self.destroy()
        except Exception as exc:
            messagebox.showerror("无法切换语言", str(exc), parent=self)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(background="#EEF8F0")
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        style.configure("Surface.TFrame", background="#F8FCF8")
        style.configure("Card.TFrame", background="#FBFDFB", relief="flat")
        style.configure("TLabel", background="#FBFDFB", foreground="#242424")
        style.configure("Title.TLabel", background="#F8FCF8", foreground="#25432E", font=("Microsoft YaHei UI", 23, "bold"))
        style.configure("Subtitle.TLabel", background="#F8FCF8", foreground="#5A6A5D", font=("Microsoft YaHei UI", 10))
        style.configure("SectionTitle.TLabel", background="#F8FCF8", foreground="#294B34", font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("Summary.TLabel", background="#F8FCF8", foreground="#2E5D3B", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Accent.TButton", background="#5A9F6D", foreground="#FFFFFF", bordercolor="#5A9F6D", focusthickness=0, padding=(16, 9), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#4B8D5D"), ("pressed", "#376E47"), ("disabled", "#AED0B7")], foreground=[("disabled", "#F5F5F5")])
        style.configure("Soft.TButton", background="#F3F8F4", foreground="#2C4935", bordercolor="#D0E0D2", focusthickness=0, padding=(12, 7))
        style.map("Soft.TButton", background=[("active", "#E8F4EA"), ("pressed", "#DCEEDF")], bordercolor=[("active", "#94BFA0")])
        style.configure("TEntry", fieldbackground="#FFFFFF", bordercolor="#CADCCE", lightcolor="#CADCCE", darkcolor="#CADCCE", padding=7)
        style.map("TEntry", bordercolor=[("focus", "#5A9F6D")])
        style.configure("TCombobox", fieldbackground="#FFFFFF", background="#F3F8F4", bordercolor="#CADCCE", arrowsize=14, padding=6)
        style.map(
            "TCombobox",
            bordercolor=[("focus", "#5A9F6D")],
            fieldbackground=[("readonly", "#FFFFFF")],
            selectbackground=[("readonly", "#FFFFFF")],
            selectforeground=[("readonly", "#26322A")],
        )
        style.configure("TCheckbutton", background="#FBFDFB", foreground="#34483A", padding=(0, 3))
        style.map("TCheckbutton", background=[("active", "#FBFDFB")])
        style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF", foreground="#2C352F", bordercolor="#D8E6DA", rowheight=32)
        style.map("Treeview", background=[("selected", "#E2F1E5")], foreground=[("selected", "#2A5A38")])
        style.configure("Treeview.Heading", background="#F1F7F2", foreground="#3E5545", relief="flat", padding=(8, 8), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Treeview.Heading", background=[("active", "#E6F1E8")])

    def _draw_gradient(self, event=None) -> None:
        canvas = self.background_canvas
        width = max(canvas.winfo_width(), 2)
        height = max(canvas.winfo_height(), 2)
        canvas.delete("gradient")
        start, end, bands = (226, 243, 230), (250, 252, 249), 48
        for index in range(bands):
            ratio = index / max(bands - 1, 1)
            color = "#{:02x}{:02x}{:02x}".format(*(int(start[c] + (end[c] - start[c]) * ratio) for c in range(3)))
            x1, x2 = int(width * index / bands), int(width * (index + 1) / bands) + 1
            canvas.create_rectangle(x1, 0, x2, height, fill=color, outline=color, tags="gradient")
        canvas.tag_lower("gradient")
        canvas.itemconfigure(self.surface_window, width=max(width - 36, 900), height=max(height - 30, 650))

    def _apply_windows11_effects(self) -> None:
        if os.name != "nt":
            return
        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            rounded, backdrop = ctypes.c_int(2), ctypes.c_int(3)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(rounded), ctypes.sizeof(rounded))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
        except Exception:
            pass

    def _build_ui(self) -> None:
        self.background_canvas = tk.Canvas(self, highlightthickness=0, background="#EEF8F0")
        self.background_canvas.pack(fill="both", expand=True)
        outer = ttk.Frame(self.background_canvas, padding=(24, 20), style="Surface.TFrame")
        self.surface_window = self.background_canvas.create_window(18, 15, anchor="nw", window=outer)
        self.background_canvas.bind("<Configure>", self._draw_gradient)

        ttk.Label(outer, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="用保留下来的依据文件，找出并安全暂存没有对应文件的另一种格式。",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 16))
        RoundedButton(
            outer,
            text="English",
            command=lambda: self._switch_language("en"),
            width=88,
            height=34,
            surface="#F8FCF8",
        ).place(relx=1.0, x=-2, y=3, anchor="ne")
        RoundedButton(
            outer,
            text="👍  GitHub · ZJ_X",
            command=lambda: webbrowser.open(AUTHOR_URL),
            width=174,
            height=34,
            surface="#F8FCF8",
            font=("Segoe UI Emoji", 10),
        ).place(relx=1.0, x=-100, y=3, anchor="ne")

        ttk.Label(outer, text="整理规则与文件夹", style="SectionTitle.TLabel").pack(
            anchor="w", pady=(0, 7)
        )
        settings_card = RoundedCard(outer, padding=16, radius=20, auto_height=True)
        settings_card.pack(fill="x")
        settings = settings_card.content
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="整理方案").grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=5
        )
        preset_bar = ttk.Frame(settings, style="Card.TFrame")
        preset_bar.grid(row=0, column=1, columnspan=3, sticky="w", pady=5)
        self.preset_combo = RoundedSelect(
            preset_bar,
            textvariable=self.preset_var,
            width=250,
            command=self._on_preset_changed,
        )
        self.preset_combo.pack(side="left")
        RoundedButton(preset_bar, text="保存当前方案…", command=self._save_preset, width=150).pack(
            side="left", padx=(8, 0)
        )
        RoundedButton(preset_bar, text="删除方案", command=self._delete_preset, width=112).pack(
            side="left", padx=(8, 0)
        )

        ttk.Label(settings, text="整理模式").grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=5
        )
        mode_combo = RoundedSelect(
            settings,
            textvariable=self.mode_var,
            values=(MODE_JPG_TO_RAW, MODE_RAW_TO_JPG, MODE_CUSTOM),
            width=230,
            command=self._on_mode_changed,
        )
        mode_combo.grid(row=1, column=1, sticky="w", pady=5)
        ttk.Label(
            settings,
            textvariable=self.mode_note_var,
            foreground="#4b5563",
            wraplength=760,
            justify="left",
        ).grid(row=2, column=1, columnspan=3, sticky="w", pady=(0, 7))

        self.reference_entry, self.reference_button = self._folder_row(
            settings,
            3,
            self.reference_folder_label_var,
            self.reference_var,
            self._choose_reference,
            extra_command=self._set_reference_to_app_dir,
            extra_text="设为程序位置",
        )
        self.reference_entry.bind("<KeyRelease>", self._on_reference_path_changed)
        self.target_entry, self.target_button = self._folder_row(
            settings,
            4,
            self.target_folder_label_var,
            self.target_var,
            self._choose_target,
        )
        self._folder_row(
            settings,
            5,
            self.quarantine_label_var,
            self.quarantine_var,
            self._choose_quarantine,
            extra_command=self._auto_quarantine,
            extra_text="自动设置",
        )

        options = ttk.Frame(settings, style="Card.TFrame")
        options.grid(row=6, column=1, columnspan=3, sticky="ew", pady=(8, 3))
        FluentCheckbutton(
            options,
            textvariable=self.same_text_var,
            variable=self.same_var,
            command=self._toggle_same_folder,
            width=500,
        ).pack(side="left")
        FluentCheckbutton(
            options,
            text="包含子文件夹",
            variable=self.recursive_var,
            command=self._invalidate_scan,
            width=190,
        ).pack(side="left", padx=(24, 0))

        formats = ttk.Frame(settings, style="Card.TFrame")
        formats.grid(row=7, column=1, columnspan=3, sticky="w", pady=(5, 0))
        ttk.Label(formats, textvariable=self.reference_ext_label_var).pack(side="left")
        reference_ext_entry = RoundedEntry(
            formats, textvariable=self.reference_ext_var, width=160
        )
        reference_ext_entry.pack(side="left", padx=(5, 24))
        ttk.Label(formats, textvariable=self.target_ext_label_var).pack(side="left")
        target_ext_entry = RoundedEntry(formats, textvariable=self.target_ext_var, width=160)
        target_ext_entry.pack(side="left", padx=(5, 0))
        reference_ext_entry.bind("<KeyRelease>", self._on_rule_changed)
        target_ext_entry.bind("<KeyRelease>", self._on_rule_changed)

        operation_bar = ttk.Frame(settings, style="Card.TFrame")
        operation_bar.grid(row=8, column=1, columnspan=3, sticky="w", pady=(8, 2))
        ttk.Label(operation_bar, text="处理方式：").pack(side="left")
        operation_combo = RoundedSelect(
            operation_bar,
            textvariable=self.operation_var,
            values=(ACTION_MOVE, ACTION_COPY, ACTION_RECYCLE),
            width=230,
            command=self._on_operation_changed,
        )
        operation_combo.pack(side="left", padx=(5, 0))
        xmp_bar = ttk.Frame(settings, style="Card.TFrame")
        xmp_bar.grid(row=9, column=1, columnspan=3, sticky="w", pady=(2, 0))
        FluentCheckbutton(
            xmp_bar,
            text="同时处理同名 XMP 文件",
            variable=self.include_xmp_var,
            command=self._on_xmp_changed,
            width=320,
        ).pack(side="left")

        action_bar = ttk.Frame(outer, style="Surface.TFrame")
        action_bar.pack(fill="x", pady=(14, 10))
        RoundedButton(
            action_bar,
            text="扫描并预览",
            command=self._scan,
            variant="accent",
            width=145,
            surface="#F8FCF8",
        ).pack(side="left")
        RoundedButton(action_bar, text="全选待移动", command=self._select_all_pending, width=145, surface="#F8FCF8").pack(
            side="left", padx=(8, 0)
        )
        RoundedButton(action_bar, text="全部取消", command=self._clear_selection, width=118, surface="#F8FCF8").pack(
            side="left", padx=(8, 0)
        )
        self.move_button = RoundedButton(
            action_bar,
            text="执行移动",
            command=self._move,
            state="disabled",
            variant="accent",
            width=125,
            surface="#F8FCF8",
        )
        self.move_button.pack(side="left", padx=8)
        RoundedButton(action_bar, text="撤销上一次操作", command=self._undo, width=145, surface="#F8FCF8").pack(
            side="left"
        )
        RoundedButton(
            action_bar, text="打开暂存文件夹", command=self._open_quarantine, width=145, surface="#F8FCF8"
        ).pack(side="right")

        self.summary_var = tk.StringVar(value="选择整理模式和文件夹，然后扫描预览。")
        ttk.Label(outer, textvariable=self.summary_var, style="Summary.TLabel").pack(
            anchor="w", pady=(0, 2)
        )
        ttk.Label(
            outer,
            textvariable=self.warning_var,
            foreground="#b91c1c",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        table_card = RoundedCard(outer, padding=8, radius=18, auto_height=False)
        table_card.pack(fill="both", expand=True)
        table_frame = table_card.content
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        columns = ("selected", "name", "folder", "status", "action")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse"
        )
        self.tree.heading("selected", text="选择")
        self.tree.heading("name", text="待整理文件")
        self.tree.heading("folder", text="相对位置")
        self.tree.heading("status", text="同名依据文件")
        self.tree.heading("action", text="处理方式")
        self.tree.column("selected", width=65, minwidth=55, anchor="center", stretch=False)
        self.tree.column("name", width=220, anchor="w")
        self.tree.column("folder", width=360, anchor="w")
        self.tree.column("status", width=160, anchor="center")
        self.tree.column("action", width=110, anchor="center")
        self.tree.tag_configure("keep", foreground="#237a3b")
        self.tree.tag_configure("move", foreground="#b45309")
        self.tree.tag_configure(
            "selected_candidate",
            foreground="#5A9F6D",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<space>", self._on_tree_space)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

    def _folder_row(
        self,
        parent,
        row: int,
        label_variable: tk.StringVar | str,
        path_variable: tk.StringVar,
        command,
        extra_command=None,
        extra_text: str = "",
    ):
        label_options = (
            {"text": label_variable}
            if isinstance(label_variable, str)
            else {"textvariable": label_variable}
        )
        ttk.Label(parent, **label_options).grid(
            row=row, column=0, sticky="w", padx=(0, 12), pady=5
        )
        entry = RoundedEntry(parent, textvariable=path_variable, width=560)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        entry.bind("<KeyRelease>", lambda _event: self._invalidate_scan())
        button = RoundedButton(parent, text="选择…", command=command, width=104)
        button.grid(row=row, column=2, padx=(8, 0), pady=5)
        if extra_command:
            RoundedButton(parent, text=extra_text, command=extra_command, width=116).grid(
                row=row, column=3, padx=(8, 0), pady=5
            )
        return entry, button

    def _all_presets(self) -> dict[str, dict]:
        presets = dict(BUILTIN_PRESETS)
        presets.update(self.custom_presets)
        return presets

    def _refresh_preset_values(self) -> None:
        values = list(BUILTIN_PRESETS) + sorted(self.custom_presets) + [CUSTOM_PRESET_LABEL]
        self.preset_combo.configure(values=values)
        if self.preset_var.get() not in values:
            self.preset_var.set(CUSTOM_PRESET_LABEL)

    def _on_preset_changed(self, _event=None) -> None:
        name = self.preset_var.get()
        if name == CUSTOM_PRESET_LABEL:
            return
        preset = self._all_presets().get(name)
        if not preset:
            return
        self._applying_preset = True
        try:
            self.mode_var.set(preset.get("mode", MODE_JPG_TO_RAW))
            self.reference_ext_var.set(preset.get("reference_extensions", ".JPG,.JPEG"))
            self.target_ext_var.set(preset.get("target_extensions", ".ARW"))
            self.operation_var.set(preset.get("operation", ACTION_MOVE))
            self.include_xmp_var.set(bool(preset.get("include_xmp", False)))
        finally:
            self._applying_preset = False
        self._update_mode_labels()
        self._update_operation_ui()
        self._invalidate_scan()

    def _save_preset(self) -> None:
        name = simpledialog.askstring(
            "保存整理方案",
            "输入方案名称，例如“我的相机：JPG → RAF”：",
            parent=self,
        )
        if not name or not name.strip():
            return
        name = name.strip()
        if name in BUILTIN_PRESETS or name == CUSTOM_PRESET_LABEL:
            messagebox.showinfo(
                "名称已保留", "内置方案名称不能覆盖，请换一个名称。", parent=self
            )
            return
        if not parse_extensions(self.reference_ext_var.get()) or not parse_extensions(
            self.target_ext_var.get()
        ):
            messagebox.showerror(
                "格式不完整", "保存方案前请填写依据格式和待整理格式。", parent=self
            )
            return
        if name in self.custom_presets and not messagebox.askyesno(
            "覆盖方案", f"方案“{name}”已经存在，是否覆盖？", parent=self
        ):
            return
        self.custom_presets[name] = {
            "mode": self.mode_var.get(),
            "reference_extensions": self.reference_ext_var.get().strip(),
            "target_extensions": self.target_ext_var.get().strip(),
            "operation": self.operation_var.get(),
            "include_xmp": self.include_xmp_var.get(),
        }
        self.preset_var.set(name)
        self._refresh_preset_values()
        self._save_current_config()
        messagebox.showinfo("方案已保存", f"已保存整理方案“{name}”。", parent=self)

    def _delete_preset(self) -> None:
        name = self.preset_var.get()
        if name in BUILTIN_PRESETS:
            messagebox.showinfo("内置方案", "内置方案不能删除。", parent=self)
            return
        if name == CUSTOM_PRESET_LABEL or name not in self.custom_presets:
            messagebox.showinfo("没有可删除方案", "请选择一个自己保存的方案。", parent=self)
            return
        if not messagebox.askyesno(
            "删除方案", f"确定删除方案“{name}”吗？", parent=self
        ):
            return
        del self.custom_presets[name]
        self.preset_var.set(CUSTOM_PRESET_LABEL)
        self._refresh_preset_values()
        self._save_current_config()

    def _mark_custom(self) -> None:
        if not self._applying_preset:
            self.preset_var.set(CUSTOM_PRESET_LABEL)

    def _on_rule_changed(self, _event=None) -> None:
        self._mark_custom()
        self._invalidate_scan()

    def _on_operation_changed(self, _event=None) -> None:
        self._mark_custom()
        self._update_operation_ui()

    def _on_xmp_changed(self) -> None:
        self._mark_custom()

    def _update_operation_ui(self) -> None:
        operation = self.operation_var.get()
        button_text = {
            ACTION_MOVE: "执行移动",
            ACTION_COPY: "执行复制",
            ACTION_RECYCLE: "移入回收站",
        }.get(operation, "执行操作")
        self.move_button.configure(text=button_text)
        self.quarantine_label_var.set(
            "暂存文件夹（回收站模式不使用）"
            if operation == ACTION_RECYCLE
            else "暂存文件夹"
        )

    def _on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return None
        if self.tree.identify_column(event.x) != "#1":
            return None
        iid = self.tree.identify_row(event.y)
        if iid:
            self._toggle_iid(iid)
        return "break"

    def _on_tree_space(self, _event=None):
        iid = self.tree.focus()
        if iid:
            self._toggle_iid(iid)
        return "break"

    def _toggle_iid(self, iid: str) -> None:
        item = self.item_by_iid.get(iid)
        if not item or item.has_reference:
            return
        if item.target_path in self.selected_paths:
            self.selected_paths.remove(item.target_path)
        else:
            self.selected_paths.add(item.target_path)
        values = list(self.tree.item(iid, "values"))
        values[0] = "☑" if item.target_path in self.selected_paths else "☐"
        self.tree.item(iid, values=values)
        self._update_selection_summary()

    def _select_all_pending(self) -> None:
        if not self.scan_result:
            return
        self.selected_paths = {
            item.target_path for item in self.scan_result.items if not item.has_reference
        }
        self._refresh_selection_marks()

    def _clear_selection(self) -> None:
        self.selected_paths.clear()
        self._refresh_selection_marks()

    def _refresh_selection_marks(self) -> None:
        for iid, item in self.item_by_iid.items():
            values = list(self.tree.item(iid, "values"))
            values[0] = (
                "—"
                if item.has_reference
                else ("☑" if item.target_path in self.selected_paths else "☐")
            )
            self.tree.item(iid, values=values)
        self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        if not self.scan_result:
            self.move_button.configure(state="disabled")
            return
        selected_count = len(self.selected_paths)
        result = self.scan_result
        self.summary_var.set(
            f"待整理文件 {result.target_count} 个   ·   保留 {result.keep_count} 个   ·   待移动 {result.move_count} 个   ·   本次已选 {selected_count} 个   ·   依据文件 {result.reference_count} 个"
        )
        if exceeds_safety_threshold(result.move_count, result.target_count):
            percentage = result.move_count / result.target_count * 100
            self.warning_var.set(
                f"⚠ 待移动文件占全部待整理文件的 {percentage:.1f}%，超过 80%，执行时会再次警告。"
            )
        else:
            self.warning_var.set("")
        self.move_button.configure(state="normal" if selected_count else "disabled")

    def _on_mode_changed(self, _event=None) -> None:
        info = self._mode_info()
        if self.mode_var.get() != MODE_CUSTOM:
            self.reference_ext_var.set(info["reference_extensions"])
            self.target_ext_var.set(info["target_extensions"])
        self._mark_custom()
        self._update_mode_labels()
        self._invalidate_scan()

    def _update_mode_labels(self) -> None:
        info = self._mode_info()
        reference_name = info["reference_name"]
        target_name = info["target_name"]
        self.reference_folder_label_var.set(f"{reference_name}（依据）文件夹")
        if self.same_var.get():
            self.reference_folder_label_var.set(
                f"{reference_name} + {target_name} 共用文件夹"
            )
            self.target_folder_label_var.set(f"{target_name} 文件夹（自动跟随）")
        else:
            self.reference_folder_label_var.set(f"{reference_name}（依据）文件夹")
            self.target_folder_label_var.set(f"{target_name}（待整理）文件夹")
        self.reference_ext_label_var.set("依据格式：")
        self.target_ext_label_var.set("待整理格式：")
        self.same_text_var.set(
            f"{reference_name} 和 {target_name} 在同一文件夹（只需设置上方共用文件夹）"
        )
        self.mode_note_var.set(info["note"])
        self.tree.heading("name", text=f"{target_name} 待整理文件")

    def _choose_folder(self, variable: tk.StringVar, title: str) -> bool:
        initial = variable.get().strip()
        if not Path(initial).is_dir():
            initial = str(Path.home())
        selected = filedialog.askdirectory(title=title, initialdir=initial)
        if selected:
            variable.set(selected)
            self._invalidate_scan()
            return True
        return False

    def _choose_reference(self) -> None:
        if self._choose_folder(self.reference_var, "选择依据文件夹"):
            if self.same_var.get():
                self.target_var.set(self.reference_var.get())
            if not self.quarantine_var.get().strip():
                self._auto_quarantine()

    def _set_reference_to_app_dir(self) -> None:
        self.reference_var.set(str(self.app_directory))
        if self.same_var.get():
            self.target_var.set(self.reference_var.get())
        self._invalidate_scan()

    def _on_reference_path_changed(self, _event=None) -> None:
        if self.same_var.get():
            self.target_var.set(self.reference_var.get())
        self._invalidate_scan()

    def _choose_target(self) -> None:
        self._choose_folder(self.target_var, "选择待整理文件夹")

    def _choose_quarantine(self) -> None:
        self._choose_folder(self.quarantine_var, "选择暂存文件夹")

    def _auto_quarantine(self) -> None:
        base_text = (
            self.reference_var.get().strip()
            if self.same_var.get()
            else self.target_var.get().strip()
        )
        if not base_text or not Path(base_text).is_dir():
            messagebox.showinfo(
                "请先选择照片文件夹",
                "先选择依据文件夹或待整理文件夹，再使用自动设置。",
                parent=self,
            )
            return
        target_name = self._mode_info()["target_name"]
        folder_name = f"{target_name}暂存" if self.mode_var.get() != MODE_CUSTOM else "待整理文件暂存"
        self.quarantine_var.set(str(Path(base_text).resolve().parent / folder_name))
        self._invalidate_scan()

    def _toggle_same_folder(self) -> None:
        state = "disabled" if self.same_var.get() else "normal"
        if self.same_var.get():
            self.target_var.set(self.reference_var.get())
        self.target_entry.configure(state=state)
        self.target_button.configure(state=state)
        self._update_mode_labels()
        self._invalidate_scan()

    def _invalidate_scan(self) -> None:
        self.scan_result = None
        self.selected_paths.clear()
        self.item_by_iid.clear()
        self.warning_var.set("")
        self.move_button.configure(state="disabled")
        self.status_var.set("设置已更改，请重新扫描。")

    def _validate_settings(
        self,
    ) -> tuple[Path, Path, Path | None, tuple[str, ...], tuple[str, ...]]:
        reference_text = self.reference_var.get().strip()
        target_text = (
            reference_text if self.same_var.get() else self.target_var.get().strip()
        )
        quarantine_text = self.quarantine_var.get().strip()
        if not reference_text:
            raise ValueError("请选择依据文件夹。")
        if not target_text:
            raise ValueError("请选择待整理文件夹。")
        if self.operation_var.get() != ACTION_RECYCLE and not quarantine_text:
            raise ValueError("请选择暂存文件夹。")

        reference_root = Path(reference_text)
        target_root = Path(target_text)
        quarantine_root = Path(quarantine_text) if quarantine_text else None
        if not reference_root.is_dir():
            raise ValueError("请选择有效的依据文件夹。")
        if not target_root.is_dir():
            raise ValueError("请选择有效的待整理文件夹。")
        if quarantine_root is not None and self.operation_var.get() != ACTION_RECYCLE:
            if quarantine_root.resolve() == target_root.resolve():
                raise ValueError("暂存文件夹不能和待整理文件夹相同。")
            if quarantine_root.resolve() == reference_root.resolve():
                raise ValueError("暂存文件夹不能和依据文件夹相同。")

        reference_extensions = parse_extensions(self.reference_ext_var.get())
        target_extensions = parse_extensions(self.target_ext_var.get())
        if not reference_extensions:
            raise ValueError("请填写依据格式，例如 .JPG。")
        if not target_extensions:
            raise ValueError("请填写待整理格式，例如 .ARW。")
        if (
            reference_root.resolve() == target_root.resolve()
            and set(reference_extensions) & set(target_extensions)
        ):
            raise ValueError("同一文件夹中，依据格式和待整理格式不能重复。")
        return (
            reference_root,
            target_root,
            quarantine_root,
            reference_extensions,
            target_extensions,
        )

    def _scan(self) -> None:
        try:
            (
                reference_root,
                target_root,
                quarantine_root,
                reference_extensions,
                target_extensions,
            ) = self._validate_settings()
            self.status_var.set("正在扫描…")
            self.update_idletasks()
            result = scan_files(
                reference_root,
                target_root,
                reference_extensions,
                target_extensions,
                self.recursive_var.get(),
                excluded_roots=(quarantine_root,)
                if quarantine_root and self.operation_var.get() != ACTION_RECYCLE
                else (),
            )
            self.scan_result = result
            self.selected_paths = {
                item.target_path for item in result.items if not item.has_reference
            }
            self.item_by_iid.clear()
            children = self.tree.get_children()
            if children:
                self.tree.delete(*children)
            for item in result.items:
                path = Path(item.target_path)
                relative_parent = Path(item.relative_path).parent
                iid = self.tree.insert(
                    "",
                    "end",
                    values=(
                        "—" if item.has_reference else "☑",
                        path.name,
                        "根目录" if str(relative_parent) == "." else str(relative_parent),
                        "已找到" if item.has_reference else "未找到",
                        item.action,
                    ),
                    tags=("keep" if item.has_reference else "move",),
                )
                self.item_by_iid[iid] = item
            self._update_selection_summary()
            self.status_var.set("扫描完成。执行前请检查待移动列表。")
        except Exception as exc:
            self.scan_result = None
            self.move_button.configure(state="disabled")
            self.status_var.set("扫描失败。")
            messagebox.showerror("无法扫描", str(exc), parent=self)

    def _move(self) -> None:
        if not self.scan_result or not self.selected_paths:
            return
        try:
            (
                _reference_root,
                target_root,
                quarantine_root,
                _reference_extensions,
                _target_extensions,
            ) = self._validate_settings()
        except Exception as exc:
            messagebox.showerror("设置有误", str(exc), parent=self)
            return

        selected_items = [
            item
            for item in self.scan_result.items
            if item.target_path in self.selected_paths and not item.has_reference
        ]
        count = len(selected_items)
        operation = self.operation_var.get()
        include_xmp = self.include_xmp_var.get()
        operation_description = {
            ACTION_MOVE: f"移动到：\n\n{quarantine_root}",
            ACTION_COPY: f"复制到：\n\n{quarantine_root}",
            ACTION_RECYCLE: "移入 Windows 回收站",
        }[operation]
        if not messagebox.askyesno(
            "确认执行",
            f"将对已勾选的 {count} 个待整理文件执行：\n\n{operation_description}\n\n"
            + ("同时处理找到的同名 XMP 文件。\n\n" if include_xmp else "")
            + "不会覆盖同名文件。是否继续？",
            icon="warning",
            parent=self,
        ):
            return
        if exceeds_safety_threshold(count, self.scan_result.target_count) and not messagebox.askyesno(
            "高比例操作警告",
            f"本次选择了 {count} 个文件，占全部 {self.scan_result.target_count} 个待整理文件的 80% 以上。\n\n"
            "这通常意味着依据文件夹或格式设置可能有误。请再次确认是否继续？",
            icon="warning",
            parent=self,
        ):
            return
        if self.scan_result.reference_count == 0 and not messagebox.askyesno(
            "没有找到依据文件",
            "依据文件夹中一个指定格式的文件都没有，因此所有待整理文件都会被列为候选。\n\n请再次确认是否继续本次操作？",
            icon="warning",
            parent=self,
        ):
            return

        try:
            self.status_var.set("正在安全处理文件…")
            self.update_idletasks()
            log_path, succeeded, xmp_count, errors = perform_file_operations(
                selected_items,
                target_root,
                quarantine_root,
                operation,
                include_xmp,
            )
            if log_path:
                self.last_log = str(log_path)
            self._save_current_config()
            if errors:
                details = "\n".join(errors[:8])
                if len(errors) > 8:
                    details += f"\n……另有 {len(errors) - 8} 个错误"
                messagebox.showwarning(
                    "部分文件处理失败",
                    f"主文件成功 {succeeded} 个，XMP 成功 {xmp_count} 个，错误 {len(errors)} 个：\n\n{details}",
                    parent=self,
                )
            else:
                restore_note = (
                    "需要恢复时请打开 Windows 回收站。"
                    if operation == ACTION_RECYCLE
                    else "需要恢复时可点击“撤销上一次操作”。"
                )
                messagebox.showinfo(
                    "操作完成",
                    f"主文件成功 {succeeded} 个，关联 XMP 成功 {xmp_count} 个。\n\n{restore_note}",
                    parent=self,
                )
            self.status_var.set(
                f"操作完成：主文件 {succeeded} 个，XMP {xmp_count} 个，错误 {len(errors)} 个。"
            )
            if operation == ACTION_COPY:
                self._clear_selection()
            else:
                self._scan()
        except Exception as exc:
            self.status_var.set("操作失败。")
            messagebox.showerror("无法执行", str(exc), parent=self)

    def _undo(self) -> None:
        if not self.last_log:
            messagebox.showinfo("没有记录", "目前没有可撤销的操作记录。", parent=self)
            return
        try:
            previous_log = json.loads(Path(self.last_log).read_text(encoding="utf-8"))
            if previous_log.get("operation") == ACTION_RECYCLE:
                messagebox.showinfo(
                    "请从 Windows 回收站恢复",
                    "上一次使用的是回收站模式。请打开 Windows 回收站选择文件并恢复。",
                    parent=self,
                )
                return
        except (OSError, ValueError, TypeError):
            pass
        if not messagebox.askyesno(
            "确认撤销",
            "将撤销上一次移动或复制操作。\n\n移动文件会恢复原位置；程序创建且未修改的副本会被移除。是否继续？",
            parent=self,
        ):
            return
        try:
            restored, errors = undo_move(Path(self.last_log))
            if errors:
                details = "\n".join(errors[:8])
                messagebox.showwarning(
                    "撤销未全部完成",
                    f"已恢复 {restored} 个，{len(errors)} 个未恢复：\n\n{details}",
                    parent=self,
                )
            else:
                messagebox.showinfo("撤销完成", f"已撤销 {restored} 个文件操作。", parent=self)
            self.status_var.set(f"撤销完成：成功 {restored} 个，失败 {len(errors)} 个。")
            self._invalidate_scan()
        except Exception as exc:
            messagebox.showerror("无法撤销", str(exc), parent=self)

    def _open_quarantine(self) -> None:
        try:
            if self.operation_var.get() == ACTION_RECYCLE:
                messagebox.showinfo(
                    "回收站模式",
                    "当前选择的是 Windows 回收站模式，不使用暂存文件夹。",
                    parent=self,
                )
                return
            text = self.quarantine_var.get().strip()
            if not text:
                raise ValueError("请先选择暂存文件夹。")
            path = Path(text)
            path.mkdir(parents=True, exist_ok=True)
            open_folder(path)
        except Exception as exc:
            messagebox.showerror("无法打开", str(exc), parent=self)

    def _save_current_config(self) -> None:
        save_config(
            {
                "mode": self.mode_var.get(),
                "reference_folder": self.reference_var.get().strip(),
                "target_folder": self.target_var.get().strip(),
                "quarantine_folder": self.quarantine_var.get().strip(),
                "same_folder": self.same_var.get(),
                "reference_extensions": self.reference_ext_var.get().strip(),
                "target_extensions": self.target_ext_var.get().strip(),
                "recursive": self.recursive_var.get(),
                "operation": self.operation_var.get(),
                "include_xmp": self.include_xmp_var.get(),
                "config_version": 4,
                "preset_name": self.preset_var.get(),
                "custom_presets": self.custom_presets,
                "last_log": self.last_log,
            }
        )

    def _on_close(self) -> None:
        try:
            self._save_current_config()
        finally:
            self.destroy()


def main() -> None:
    app = PhotoOrganizerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
