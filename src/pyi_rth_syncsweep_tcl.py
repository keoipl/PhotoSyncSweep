"""Initialize the application-local Tcl library before importing Tkinter."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


def _initialize_bundled_tcl() -> None:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    dll_candidates = (
        bundle_root / "tcl86t.dll",
        bundle_root / "DLLs" / "tcl86t.dll",
    )
    library_candidates = (
        bundle_root / "_tcl_data",
        bundle_root / "tcl" / "tcl8.6",
    )
    dll_path = next((path for path in dll_candidates if path.is_file()), None)
    library_path = next((path for path in library_candidates if path.is_dir()), None)
    if dll_path is None or library_path is None:
        return
    try:
        tcl = ctypes.WinDLL(str(dll_path))
        tcl.Tcl_FindExecutable.argtypes = [ctypes.c_char_p]
        tcl.Tcl_FindExecutable(str(Path(sys.executable)).encode("utf-8"))
        tcl.Tcl_NewStringObj.argtypes = [ctypes.c_char_p, ctypes.c_int]
        tcl.Tcl_NewStringObj.restype = ctypes.c_void_p
        tcl.TclSetLibraryPath.argtypes = [ctypes.c_void_p]
        library_bytes = library_path.as_posix().encode("utf-8")
        library_object = tcl.Tcl_NewStringObj(library_bytes, len(library_bytes))
        tcl.TclSetLibraryPath(library_object)
    except (AttributeError, OSError):
        pass


_initialize_bundled_tcl()
