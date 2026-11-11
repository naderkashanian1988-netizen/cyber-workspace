# CYBER WORKSPACE — Windows build pipeline (PowerShell 5.1+, Windows 10/11 x64)
# Produces:
#   dist\CyberWorkspace\CyberWorkspace.exe                (portable, PyInstaller onedir)
#   Installer\Windows\CyberWorkspace-1.0.0-rc.1-setup.exe (when Inno Setup 6 is present)
# Usage (from anywhere):
#   powershell -ExecutionPolicy Bypass -File Build\Scripts\build_windows.ps1
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # repository root
Set-Location $repo

Write-Host "== CYBER WORKSPACE Windows build (v1.0.0-rc.1) ==" -ForegroundColor Green

# 1. pinned, reproducible environment
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r Source\Windows\requirements.txt
.\.venv\Scripts\python.exe -m pip install "pyinstaller==6.11.1"

# 2. tests must pass before any artifact is built
Push-Location Source\Windows
.\..\..\.venv\Scripts\python.exe -m pytest tests -q
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "tests failed - refusing to build" }
Pop-Location

# 3. freeze the application (spec resolves its own paths; CWD-independent)
.\.venv\Scripts\pyinstaller.exe Build\Configuration\cyber_workspace.spec `
    --distpath dist --workpath build --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

# 4. optional: Inno Setup installer -> Installer\Windows\
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
    & $iscc Build\Configuration\cyber_workspace.iss
    if ($LASTEXITCODE -ne 0) { throw "inno setup failed" }
    Write-Host "installer written to Installer\Windows\" -ForegroundColor Green
} else {
    Write-Host "Inno Setup not found - skipped .exe installer (portable build in dist\)" -ForegroundColor Yellow
}

Write-Host "DONE. Portable app: dist\CyberWorkspace\CyberWorkspace.exe" -ForegroundColor Green
