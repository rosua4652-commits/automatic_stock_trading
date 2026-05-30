# Quick fix - run in project folder if run.bat used Python 3.14 by mistake
# powershell -ExecutionPolicy Bypass -File fix-venv.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py312 = $null
try {
    $py312 = (& py -3.12 -c "import sys; print(sys.executable)").Trim()
} catch {}

if (-not $py312 -or -not (Test-Path $py312)) {
    Write-Host "ERROR: py -3.12 not found. Install Python 3.12 first."
    Read-Host "Press Enter"
    exit 1
}

Write-Host "Python 3.12: $py312"
& $py312 --version

if (Test-Path "backend\.venv") {
    Write-Host "Removing old venv..."
    Remove-Item -Recurse -Force "backend\.venv"
}

Write-Host "Creating venv with 3.12..."
& $py312 -m venv "backend\.venv"

$venvPy = "backend\.venv\Scripts\python.exe"
& $venvPy --version

Write-Host "Installing packages..."
& $venvPy -m pip install -q --upgrade pip
& "backend\.venv\Scripts\pip.exe" install -q --no-cache-dir -r backend\requirements.txt

Write-Host ""
Write-Host "Done. Now run:  run.bat"
Read-Host "Press Enter"
