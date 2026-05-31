# Download GitHub main ZIP and update project (no git required).
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
$repo = "rosua4652-commits/automatic_stock_trading"
$branch = "main"
$zipUrl = "https://github.com/$repo/archive/refs/heads/$branch.zip"

Write-Host ""
Write-Host "  AIDI — GitHub ZIP update (no git)"
Write-Host "  ================================="
Write-Host "  Repo: $repo ($branch)"
Write-Host ""

$temp = Join-Path $env:TEMP ("aidi-update-" + [guid]::NewGuid().ToString("n"))
$zipPath = Join-Path $temp "repo.zip"
$extractRoot = Join-Path $temp "extract"
New-Item -ItemType Directory -Path $temp -Force | Out-Null

try {
    Write-Host "  Downloading..."
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    Write-Host "  Extracting..."
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    $src = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
    if (-not $src) { throw "ZIP extract failed" }

    $skipNames = @(
        "backend\data",
        "backend\.venv",
        "logs",
        "frontend\node_modules",
        "frontend\dist"
    )

    Write-Host "  Copying files (settings/data kept)..."
    $allFiles = Get-ChildItem -LiteralPath $src.FullName -Recurse -File
    foreach ($f in $allFiles) {
        $rel = $f.FullName.Substring($src.FullName.Length).TrimStart("\", "/")
        $skip = $false
        foreach ($s in $skipNames) {
            if ($rel -ieq $s -or $rel -like ($s + "\*") -or $rel -like ($s + "/*")) {
                $skip = $true
                break
            }
        }
        if ($skip) { continue }
        $dest = Join-Path $RepoRoot $rel
        $destDir = Split-Path $dest -Parent
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
        Copy-Item -LiteralPath $f.FullName -Destination $dest -Force
    }

    Remove-Item -LiteralPath (Join-Path $RepoRoot "backend\.aidi-prep-state") -Force -ErrorAction SilentlyContinue
    $build = $null
    $mainPy = Join-Path $RepoRoot "backend\app\main.py"
    if (Test-Path $mainPy) {
        $t = Get-Content $mainPy -Raw
        if ($t -match 'AIDI_BUILD\s*=\s*"([^"]+)"') { $build = $matches[1] }
    }
    Write-Host ""
    Write-Host "  Done. Build: $build"
    Write-Host "  Next: run.bat  (will rebuild frontend if needed)"
    Write-Host ""
} catch {
    Write-Host ""
    Write-Host "  ERROR: $($_.Exception.Message)"
    Write-Host ""
    Write-Host "  If the repo is private, download ZIP in browser while logged in,"
    Write-Host "  extract, and copy files into this folder manually."
    Write-Host ""
    exit 1
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}

exit 0
