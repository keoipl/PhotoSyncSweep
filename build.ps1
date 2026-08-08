$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceRoot = Join-Path $ProjectRoot "src"
$DistRoot = Join-Path $ProjectRoot "dist"
$BuildRoot = Join-Path $ProjectRoot ".build"
$AppName = "Photo SyncSweep 照片联动清理助手"

Set-Location $ProjectRoot
$env:PYTHONPATH = $SourceRoot

python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --noupx `
    --name $AppName `
    --icon photo_organizer.ico `
    --version-file version_info.txt `
    --manifest app.manifest `
    --runtime-hook src/pyi_rth_syncsweep_tcl.py `
    --paths src `
    --hidden-import photo_organizer_en `
    --hidden-import photo_organizer_v3 `
    --distpath $DistRoot `
    --workpath $BuildRoot `
    src/photo_syncsweep_standalone.py

Write-Host "Build complete: $DistRoot\$AppName.exe"
