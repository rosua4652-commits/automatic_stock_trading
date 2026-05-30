# Apply a ZIP you downloaded from GitHub (browser) - works with PRIVATE repo
param(
    [string]$ZipPath = ""
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }
Set-Location -LiteralPath $Root

. (Join-Path $PSScriptRoot "scripts\pc_apply_update.ps1")

Write-Host ""
Write-Host " AIDI - apply manual GitHub ZIP"
Write-Host " =============================="
Write-Host " Project: $Root"
Write-Host ""

if (-not $ZipPath -and $args.Count -gt 0) { $ZipPath = $args[0] }

if (-not $ZipPath) {
    $candidates = @()
    $candidates += Get-ChildItem -LiteralPath $Root -Filter "*.zip" -File -ErrorAction SilentlyContinue
    $dl = Join-Path $env:USERPROFILE "Downloads"
    if (Test-Path -LiteralPath $dl) {
        $candidates += Get-ChildItem -LiteralPath $dl -Filter "automatic_stock_trading*.zip" -File -ErrorAction SilentlyContinue
    }
    $pick = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($pick) {
        $ZipPath = $pick.FullName
        Write-Host "Using newest ZIP: $ZipPath"
    }
}

if (-not $ZipPath) {
    Write-Host "No ZIP found."
    Write-Host ""
    Write-Host "1. Log in at https://github.com"
    Write-Host "2. Open automatic_stock_trading repository"
    Write-Host "3. Code -> Download ZIP"
    Write-Host "4. Run this again, or:"
    Write-Host '   apply-manual-zip.bat "C:\Users\...\automatic_stock_trading-main.zip"'
    Read-Host "Press Enter"
    exit 1
}

try {
    Apply-AidiUpdateFromZip -ZipPath $ZipPath -Root $Root
} catch {
    Write-Host ""
    Write-Host $_.Exception.Message
    Read-Host "Press Enter"
    exit 1
}

Write-Host ""
Write-Host "Next: run.bat"
Read-Host "Press Enter"
exit 0
