# Changelog

## 1.0.0 — 2026-08-08

First public release of Photo SyncSweep.

### Added

- JPG → RAW, RAW → JPG, and custom extension matching.
- Preview list with per-file selection.
- Move, copy, and Windows Recycle Bin actions.
- Optional same-name XMP sidecar handling, disabled by default.
- Sony ARW, Canon CR3, and Nikon NEF presets with custom preset saving.
- Recursive scanning with relative-folder preservation.
- 80% high-risk warning and execution confirmation.
- Undo support for move and safe-copy operations.
- Combined English and Chinese application with saved language preference.
- Pale-green Fluent 2 inspired interface and custom application icon.
- Standalone 64-bit Windows executable with embedded Python and Tk runtime.

### Fixed

- Language switching now starts a clean embedded runtime, preventing repeated English/Chinese switching from losing the packaged Python interpreter.
