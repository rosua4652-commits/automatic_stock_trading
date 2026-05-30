# AIDI - GitHub main ZIP -> current folder (works only if repo is PUBLIC)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }
Set-Location -LiteralPath $Root

. (Join-Path $PSScriptRoot "scripts\pc_apply_update.ps1")

Write-Host ""
Write-Host " AIDI - download latest from GitHub"
Write-Host " =================================="
Write-Host " Target: $Root"
Write-Host ""

$zipUrl = "https://github.com/rosua4652-commits/automatic_stock_trading/archive/refs/heads/main.zip"
$temp = Join-Path $env:TEMP ("aidi-dl-" + [Guid]::NewGuid().ToString("n"))
$zip = Join-Path $temp "main.zip"
New-Item -ItemType Directory -Force -Path $temp | Out-Null

Write-Host "[download] $zipUrl"
try {
    Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing
} catch {
    Write-Host ""
    Write-Host "Download failed. If repo is PRIVATE, use apply-manual-zip.bat"
    Write-Host "  (GitHub website -> Code -> Download ZIP while logged in)"
    Write-Host $_.Exception.Message
    Read-Host "Press Enter"
    exit 1
}

try {
    Apply-AidiUpdateFromZip -ZipPath $zip -Root $Root
} catch {
    Write-Host ""
    Write-Host $_.Exception.Message
    Write-Host ""
    Write-Host "Use apply-manual-zip.bat with a ZIP from GitHub (browser, logged in)."
    Read-Host "Press Enter"
    exit 1
}

Write-Host ""
Write-Host "Next: run.bat"
Read-Host "Press Enter"
exit 0
