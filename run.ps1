# AIDI - Windows PowerShell (if run.bat fails, use this)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Port = if ($env:PORT_OVERRIDE) { $env:PORT_OVERRIDE } else { "8000" }

Write-Host ""
Write-Host " AIDI - Windows"
Write-Host " =============="
Write-Host ""

function Get-PythonCmd {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            & py -3.12 -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { return @("py", "-3.12") }
        } catch {}
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    return $null
}

function Test-PyVersion {
    param([string[]]$Cmd)
    & @Cmd -c "import sys; v=sys.version_info; raise SystemExit(0 if (3,11)<=v[:2]<(3,14) else 1)"
    return ($LASTEXITCODE -eq 0)
}

$pyCmd = Get-PythonCmd
if (-not $pyCmd) {
    Write-Host "ERROR: Python not found. Install Python 3.12 from python.org"
    Read-Host "Press Enter"
    exit 1
}

if (-not (Test-PyVersion $pyCmd)) {
    Write-Host ""
    Write-Host "ERROR: Need Python 3.11 or 3.12. Python 3.14 is NOT supported."
    Write-Host "Install 3.12, then: Remove-Item -Recurse -Force backend\.venv"
    Read-Host "Press Enter"
    exit 1
}

if (-not (Test-Path "backend\app\main.py")) {
    Write-Host "ERROR: Run from project root (backend\app\main.py missing)"
    Read-Host "Press Enter"
    exit 1
}

$venvPy = "backend\.venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    if (-not (Test-PyVersion @($venvPy))) {
        Write-Host "Removing old venv (wrong Python version)..."
        Remove-Item -Recurse -Force "backend\.venv"
    }
}

if (-not (Test-Path $venvPy)) {
    Write-Host "Creating venv..."
    & @pyCmd -m venv backend\.venv
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
