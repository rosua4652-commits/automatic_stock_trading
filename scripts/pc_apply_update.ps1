# Shared: apply GitHub ZIP layout into AIDI project root (keeps credentials + venv)
function Apply-AidiUpdateFromZip {
    param(
        [Parameter(Mandatory = $true)][string]$ZipPath,
        [Parameter(Mandatory = $true)][string]$Root
    )

    $ZipPath = $ZipPath.Trim('"')
    $Root = $Root.TrimEnd('\')

    if (-not (Test-Path -LiteralPath $ZipPath)) {
        throw "ZIP not found: $ZipPath"
    }

    $bytes = [System.IO.File]::ReadAllBytes($ZipPath)
    if ($bytes.Length -lt 4 -or $bytes[0] -ne 0x50 -or $bytes[1] -ne 0x4B) {
        $preview = ""
        try { $preview = [System.Text.Encoding]::UTF8.GetString($bytes[0..([Math]::Min(200, $bytes.Length - 1))]) } catch {}
        if ($preview -match "404|Not Found") {
            throw @"
This is not a ZIP file (GitHub returned 404 Not Found).
The repository is PRIVATE or the URL is wrong.
Fix: log in at github.com, Code -> Download ZIP, then run apply-manual-zip.bat
"@
        }
        throw "Not a valid ZIP file: $ZipPath"
    }

    if (-not (Test-Path -LiteralPath (Join-Path $Root "backend\app\main.py"))) {
        throw "Not an AIDI project folder (missing backend\app\main.py): $Root"
    }

    $temp = Join-Path $env:TEMP ("aidi-apply-" + [Guid]::NewGuid().ToString("n"))
    $credPath = Join-Path $Root "backend\data\credentials.json"
    $credBackup = Join-Path $temp "credentials.json.bak"
    $dataDir = Join-Path $Root "backend\data"

    New-Item -ItemType Directory -Force -Path $temp | Out-Null

    if (Test-Path -LiteralPath $credPath) {
        Copy-Item -LiteralPath $credPath -Destination $credBackup -Force
        Write-Host "[OK] Backed up credentials.json"
    }

    Write-Host "[1/3] Extracting ZIP..."
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $temp -Force

    $src = Join-Path $temp "automatic_stock_trading-main"
    if (-not (Test-Path -LiteralPath $src)) {
        $src = (Get-ChildItem -LiteralPath $temp -Directory | Select-Object -First 1).FullName
    }
    if (-not (Test-Path -LiteralPath (Join-Path $src "backend\app\main.py"))) {
        throw "ZIP layout invalid (no backend\app\main.py inside)."
    }

    Write-Host "[2/3] Copying into: $Root"
    if (-not (Test-Path -LiteralPath $dataDir)) {
        New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    }

    if (Get-Command robocopy -ErrorAction SilentlyContinue) {
        & robocopy $src $Root /E /IS /IT /XD "backend\.venv" "backend\data" ".git" "node_modules" "frontend\node_modules" "__pycache__" | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }
    } else {
        throw "robocopy not found"
    }

    if (Test-Path -LiteralPath $credBackup) {
        Copy-Item -LiteralPath $credBackup -Destination $credPath -Force
        Write-Host "[OK] Restored credentials.json"
    }

    Write-Host "[3/3] Verifying..."
    $mainPy = Join-Path $Root "backend\app\main.py"
    $build = ""
    $m = Select-String -Path $mainPy -Pattern 'AIDI_BUILD\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($m) { $build = $m.Matches.Groups[1].Value }
    Write-Host "Done. AIDI_BUILD = $build"

    try { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue } catch {}
}
