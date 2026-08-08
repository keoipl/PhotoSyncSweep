<div align="center">
  <img src="docs/images/app-icon.png" width="150" alt="Photo SyncSweep icon">
  <h1>Photo SyncSweep</h1>
  <p>Safely organize matching JPG, RAW, and XMP files after photo culling.</p>
  <p><a href="README.md">简体中文</a> · <a href="https://github.com/keoipl/PhotoSyncSweep/releases">Download</a></p>
</div>

![Version](https://img.shields.io/badge/version-1.0.0-6FAF7B)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-6FAF7B)
![Architecture](https://img.shields.io/badge/architecture-x64-6FAF7B)
![Python](https://img.shields.io/badge/source-Python%203.12%2B-6FAF7B)

## Overview

Photo SyncSweep is a Windows desktop utility for photography culling workflows. Cull and delete unwanted JPG previews first, then find RAW files that no longer have a same-name JPG. You can also reverse the direction or define any custom reference and target extensions.

Scanning never modifies files. Every candidate is shown in a preview list and can be selected individually before an action is performed.

## Features

- JPG → RAW, RAW → JPG, and fully custom matching modes.
- Built-in Sony ARW, Canon CR3, and Nikon NEF presets, plus saved custom presets.
- Per-file selection with all candidates selected by default.
- Move to a holding folder, copy to a holding folder, or send to Windows Recycle Bin.
- Optional same-name XMP sidecar processing, disabled by default.
- Strong warning and second confirmation when candidates exceed 80% of target files.
- Shared or separate folders, with optional recursive subfolder scanning.
- Undo for move and safe-copy actions; existing destination files are never overwritten.
- English and Chinese in one application with one-click switching and saved preference.
- Pale-green Windows 11 / Fluent 2 inspired interface.
- Fully local operation with no telemetry or automatic uploads.

## Download

1. Open [Releases](https://github.com/keoipl/Photo-SyncSweep/releases).
2. Download `Photo SyncSweep 照片联动清理助手.exe` or the Windows x64 ZIP package.
3. Run the EXE directly. Python is not required.

The current build supports 64-bit Windows 10/11. It is not commercially code-signed, so Windows may show an “Unknown publisher” warning on first launch. Verify the download source before choosing “More info → Run anyway.”

## Typical workflow

1. Choose a preset or match direction.
2. Select reference and target folders, or enable the shared-folder option.
3. Choose a file action and holding folder.
4. Select **Scan and preview**.
5. Review the list and clear any file that should not be processed.
6. Confirm the paths and counts, then run the action.

Test a new rule with a small copy of your photos first.

## Example

Given these files:

```text
DSC001.JPG
DSC001.ARW
DSC002.ARW
```

In `JPG → RAW` mode, `DSC002.ARW` becomes a candidate because it has no same-name JPG. `DSC001.ARW` is preserved.

## Safety

- Preview-first workflow.
- Per-file selection.
- High-risk warning above 80%.
- No overwriting of same-name destination files.
- Relative folder structure preserved in recursive mode.
- XMP handling disabled by default.
- Settings and logs stay in `%APPDATA%\PhotoRawSync`, not in photo folders.

## Run from source

Windows, Python 3.12+, and Tkinter are required:

```powershell
$env:PYTHONPATH = "src"
python src/photo_syncsweep_standalone.py
```

Run tests:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

Build the standalone executable:

```powershell
.\build.ps1
```

## Privacy

Photo SyncSweep does not upload photos, file names, paths, or usage data and does not access the network automatically. The author profile opens in the default browser only when the GitHub button is clicked. See [PRIVACY.md](PRIVACY.md).

## Author

**ZJ_X** — [GitHub @keoipl](https://github.com/keoipl)

If Photo SyncSweep helps your workflow, consider starring the repository.
