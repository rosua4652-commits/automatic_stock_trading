# AIDI - GitHub main ZIP -> current folder (PC update without git)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }
Set-Location -LiteralPath $Root

Write-Host ""
Write-Host " AIDI - download latest from GitHub"
Write-Host " =================================="
Write-Host " Target folder: $Root"
Write-Host ""

if (-not (Test-Path -LiteralPath (Join-Path $Root "backend\app\main.py"))) {
    Write-Host "ERROR: backend\app\main.py not found."
    Write-Host "Open this folder in Explorer, then run again:"
    Write-Host "  C:\Users\dongil-3\Downloads\automatic_stock_trading-main (3)\automatic_stock_trading-main"
    Read-Host "Press Enter"
    exit 1
}

$zipUrl = "https://github.com/rosua4652-commits/automatic_stock_trading/archive/refs/heads/main.zip"
$temp = Join-Path $env:TEMP ("aidi-dl-" + [Guid]::NewGuid().ToString("n"))
$zip = Join-Path $temp "main.zip"
$credPath = Join-Path $Root "backend\data\credentials.json"
$credBackup = Join-Path $temp "credentials.json.bak"
$dataDir = Join-Path $Root "backend\data"

New-Item -ItemType Directory -Force -Path $temp | Out-Null

if (Test-Path -LiteralPath $credPath) {
    Copy-Item -LiteralPath $credPath -Destination $credBackup -Force
    Write-Host "[OK] Backed up backend\data\credentials.json"
}

Write-Host "[1/4] Downloading ZIP from GitHub..."
try {
    Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing
} catch {
    Write-Host "ERROR: Download failed. Check internet / firewall."
    Write-Host $_.Exception.Message
    Read-Host "Press Enter"
    exit 1
}

Write-Host "[2/4] Extracting..."
Expand-Archive -LiteralPath $zip -DestinationPath $temp -Force
$src = Join-Path $temp "automatic_stock_trading-main"
if (-not (Test-Path -LiteralPath $src)) {
    $src = (Get-ChildItem -LiteralPath $temp -Directory | Where-Object { $_.Name -ne "automatic_stock_trading-main" } | Select-Object -First 1).FullName
    if (-not $src) {
        $src = (Get-ChildItem -LiteralPath $temp -Directory | Select-Object -First 1).FullName
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $src "backend\app\main.py"))) {
    Write-Host "ERROR: Bad ZIP layout."
    Read-Host "Press Enter"
    exit 1
}

Write-Host "[3/4] Copying files into this folder..."
if (-not (Test-Path -LiteralPath $dataDir)) {
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
}

$robo = Get-Command robocopy -ErrorAction SilentlyContinue
if ($robo) {
    & robocopy $src $Root /E /IS /IT /XD "backend\.venv" "backend\data" ".git" "node_modules" "frontend\node_modules" "__pycache__" | Out-Null
    if ($LASTEXITCODE -ge 8) {
        Write-Host "ERROR: robocopy failed with code $LASTEXITCODE"
        Read-Host "Press Enter"
        exit 1
    }
} else {
    Get-ChildItem -LiteralPath $src -Force | ForEach-Object {
        $name = $_.Name
        if ($name -in @(".git", "node_modules")) { return }
        $dest = Join-Path $Root $name
        if ($_.PSIsContainer) {
            if ($name -eq "backend") {
                Get-ChildItem -LiteralPath $_.FullName -Force | ForEach-Object {
                    if ($_.Name -eq "data" -or $_.Name -eq ".venv") { return }
                    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dest $_.Name) -Recurse -Force
                }
            } else {
                Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
            }
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
        }
    }
}

if (Test-Path -LiteralPath $credBackup) {
    Copy-Item -LiteralPath $credBackup -Destination $credPath -Force
    Write-Host "[OK] Restored credentials.json"
}

Write-Host "[4/4] Verifying build..."
$mainPy = Join-Path $Root "backend\app\main.py"
$build = ""
if (Test-Path -LiteralPath $mainPy) {
    $m = Select-String -Path $mainPy -Pattern 'AIDI_BUILD\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($m) { $build = $m.Matches.Groups[1].Value }
}
Write-Host ""
Write-Host " Done. AIDI_BUILD in main.py: $build"
Write-Host " Next: double-click run.bat or SETUP_PC.bat"
Write-Host ""

try {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
} catch {}

Read-Host "Press Enter"
exit 0
