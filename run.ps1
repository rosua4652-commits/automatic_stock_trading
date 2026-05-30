# AIDI - Windows PowerShell (if run.bat fails, use this)
# Right-click -> Run with PowerShell, or:  powershell -ExecutionPolicy Bypass -File run.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Port = if ($env:PORT_OVERRIDE) { $env:PORT_OVERRIDE } else { "8000" }

Write-Host ""
Write-Host " AIDI - Windows"
Write-Host " =============="
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install from https://www.python.org/downloads/"
    Read-Host "Press Enter"
    exit 1
}

if (-not (Test-Path "backend\app\main.py")) {
    Write-Host "ERROR: Run from project root (backend\app\main.py missing)"
    Read-Host "Press Enter"
    exit 1
}

$venvPy = "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating venv..."
    python -m venv backend\.venv
}

Write-Host "Installing Python packages..."
& $venvPy -m pip install -q --upgrade pip
& "backend\.venv\Scripts\pip.exe" install -q --no-cache-dir -r backend\requirements.txt

if (-not (Test-Path "frontend\dist\index.html")) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: No frontend\dist and no npm. Install Node.js or use zip with dist."
        Read-Host "Press Enter"
        exit 1
    }
    Write-Host "Building frontend..."
    Push-Location frontend
    if (-not (Test-Path node_modules)) { npm install }
    npm run build
    Pop-Location
}

if (-not (Test-Path "frontend\dist\index.html")) {
    Write-Host "ERROR: frontend\dist\index.html missing"
    Read-Host "Press Enter"
    exit 1
}

New-Item -ItemType Directory -Force -Path "backend\data" | Out-Null

Write-Host ""
Write-Host " Open: http://127.0.0.1:$Port"
Write-Host " Stop: Ctrl+C"
Write-Host ""

Set-Location backend
& "..\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port $Port
