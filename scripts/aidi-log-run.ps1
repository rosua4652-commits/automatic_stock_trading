# AIDI uvicorn — console + log file
param(
    [int]$Port = 8000,
    [string]$LogMain = "",
    [string]$LogDay = ""
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")

$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "ERROR: $py not found"
    exit 1
}

function Write-TeeLine {
    param([string]$Line)
    if ($null -eq $Line) { return }
    Write-Host $Line
    # AIDI 앱 로그는 이미 타임스탬프 포함
    if ($Line -match '\| AIDI \|') {
        $row = $Line
    } else {
        $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $row = "[$ts] $Line"
    }
    if ($LogMain) {
        Add-Content -LiteralPath $LogMain -Value $row -Encoding UTF8
    }
    if ($LogDay -and ($LogDay -ne $LogMain)) {
        Add-Content -LiteralPath $LogDay -Value $row -Encoding UTF8
    }
}

Write-TeeLine "uvicorn app.main:app --host 0.0.0.0 --port $Port"

$bindErr = $false
& $py -m uvicorn app.main:app --host 0.0.0.0 --port $Port 2>&1 | ForEach-Object {
    $line = [string]$_
    Write-TeeLine $line
    if ($line -match '10048|Address already in use|bind on address') {
        $bindErr = $true
    }
}

$code = $LASTEXITCODE
if ($null -eq $code) { $code = 0 }
if ($bindErr -and $code -eq 0) { $code = 1 }

if ($bindErr) {
    Write-TeeLine "PORT $Port already in use. Close run.bat or run: stop-aidi.bat"
}

Write-TeeLine "process exit $code"
exit $code
