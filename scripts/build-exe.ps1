# Build the School Finance desktop .exe (ticket 13).
# Output: dist\SchoolFinance.exe — single-file, hidden window, offline assets.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    py -3 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-desktop.txt
.\.venv\Scripts\python.exe packaging\generate_icon.py
.\.venv\Scripts\python.exe -m PyInstaller packaging\SchoolFinance.spec --noconfirm --clean

Write-Host ""
Write-Host "Built: $root\dist\SchoolFinance.exe"
Write-Host "Data (DB, backups, logo) is created in a 'data' folder next to the exe on first run."
