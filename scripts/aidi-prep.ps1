# AIDI run prep: build check, optional git pull, venv/pip/fe only when needed.
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"

function Write-Info([string]$Msg) {
    if (-not $Quiet) { Write-Host $Msg }
}

function Test-GitInstalled {
    return [bool](Get-Command git -ErrorAction SilentlyContinue)
}

function Read-BuildId([string]$Path, [string]$Pattern) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ($text -match $Pattern) { return $matches[1].Trim() }
    return $null
}

function Get-RemoteBuildFromGit([string]$Root, [string]$Ref = "origin/main") {
    if (-not (Test-GitInstalled)) { return $null }
    $gitDir = Join-Path $Root ".git"
    if (-not (Test-Path -LiteralPath $gitDir)) { return $null }
    Push-Location $Root
    try {
        git fetch origin -q 2>$null | Out-Null
        $content = git show "${Ref}:backend/app/main.py" 2>$null
        if ($content -match 'AIDI_BUILD\s*=\s*"([^"]+)"') {
            return $matches[1].Trim()
        }
    } finally {
        Pop-Location
    }
    return $null
}

function Get-RemoteBuildId([string]$Root) {
    $fromGit = Get-RemoteBuildFromGit $Root
    if ($fromGit) { return $fromGit }

    $repo = "rosua4652-commits/automatic_stock_trading"
    $branch = "main"
    $gitDir = Join-Path $Root ".git"
    if ((Test-Path -LiteralPath $gitDir) -and (Test-GitInstalled)) {
        Push-Location $Root
        try {
            $origin = (git remote get-url origin 2>$null)
            if ($origin -match "github\.com[:/]([^/]+/[^/\s]+)") {
                $repo = $matches[1] -replace "\.git$", ""
            }
            $b = (git rev-parse --abbrev-ref HEAD 2>$null)
            if ($b) { $branch = $b.Trim() }
        } finally {
            Pop-Location
        }
    }
    $cacheBust = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $url = "https://raw.githubusercontent.com/$repo/$branch/backend/app/main.py?t=$cacheBust"
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 12
        if ($resp.Content -match 'AIDI_BUILD\s*=\s*"([^"]+)"') {
            return $matches[1].Trim()
        }
    } catch {
        return $null
    }
    return $null
}

function Show-ZipUpdateHelp([string]$RemoteBuild, [string]$LocalBuild) {
    Write-Host ""
    Write-Host "  GitHub 최신 빌드와 PC 폴더가 다릅니다."
    Write-Host "  Git 이 없으므로 자동 pull 은 할 수 없습니다."
    Write-Host ""
    Write-Host "  [방법 1] update-zip.bat 실행 (ZIP 자동 받기, 권장)"
    Write-Host "  [방법 2] 브라우저에서 ZIP 받아 이 폴더에 덮어쓰기"
    Write-Host "           https://github.com/rosua4652-commits/automatic_stock_trading"
    Write-Host "           Code -> Download ZIP"
    Write-Host ""
    Write-Host "  GitHub: $RemoteBuild"
    Write-Host "  PC    : $LocalBuild"
    Write-Host ""
}

function Find-Python312 {
    $py = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $out = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { $py = $out.Trim() }
    }
    if (-not $py -and (Get-Command python -ErrorAction SilentlyContinue)) {
        $out = & python -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            & $out -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { $py = $out.Trim() }
        }
    }
    return $py
}

function Ensure-Venv([string]$Root, [string]$Py312) {
    $venvPy = Join-Path $Root "backend\.venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) {
        & $venvPy -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Info "  Removing venv (not Python 3.12)..."
            Remove-Item -LiteralPath (Join-Path $Root "backend\.venv") -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not (Test-Path -LiteralPath $venvPy)) {
        Write-Info "  Creating Python 3.12 venv..."
        & $Py312 -m venv (Join-Path $Root "backend\.venv")
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
    }
    return $venvPy
}

function Install-Pip([string]$VenvPy, [string]$Root) {
    Write-Info "  Installing Python packages..."
    & $VenvPy -m pip install -q --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
    & (Join-Path (Split-Path $VenvPy) "pip.exe") install -q --no-cache-dir -r (Join-Path $Root "backend\requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

function Build-Frontend([string]$Root, [string]$BuildId) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm not found — install Node.js for frontend build"
    }
    $fe = Join-Path $Root "frontend"
    if (-not (Test-Path (Join-Path $fe "node_modules"))) {
        Write-Info "  npm install (first time)..."
        Push-Location $fe
        & npm install
        if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install failed" }
        Pop-Location
    }
    Write-Info "  Building frontend ($BuildId)..."
    Push-Location $fe
    & npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm run build failed" }
    Pop-Location
    $stamp = Join-Path $fe "dist\.aidi-ui-build"
    Set-Content -LiteralPath $stamp -Value $BuildId -Encoding ascii -NoNewline
}

function Test-FastReady(
    [string]$LocalBuild,
    [string]$UiSrc,
    [string]$DistStamp,
    [bool]$VenvOk,
    [bool]$DistOk
) {
    if (-not $LocalBuild -or -not $VenvOk -or -not $DistOk) { return $false }
    if ($UiSrc -and $UiSrc -ne $LocalBuild) { return $false }
    if ($DistStamp -ne $LocalBuild -and $DistStamp -ne $UiSrc) { return $false }
    return $true
}

# --- main ---
$mainPy = Join-Path $RepoRoot "backend\app\main.py"
if (-not (Test-Path -LiteralPath $mainPy)) {
    Write-Host "ERROR: backend\app\main.py not found"
    exit 2
}

$localBuild = Read-BuildId $mainPy 'AIDI_BUILD\s*=\s*"([^"]+)"'
$uiSrc = Read-BuildId (Join-Path $RepoRoot "frontend\src\uiBuild.ts") 'UI_BUILD\s*=\s*"([^"]+)"'
$stampPath = Join-Path $RepoRoot "frontend\dist\.aidi-ui-build"
$distStamp = ""
if (Test-Path -LiteralPath $stampPath) {
    $distStamp = (Get-Content -LiteralPath $stampPath -Raw -Encoding UTF8).Trim()
}
$venvPy = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
$venvOk = Test-Path -LiteralPath $venvPy
$distOk = Test-Path (Join-Path $RepoRoot "frontend\dist\index.html")

$remoteBuild = Get-RemoteBuildId $RepoRoot
$statePath = Join-Path $RepoRoot "backend\.aidi-prep-state"
$lastOk = ""
if (Test-Path -LiteralPath $statePath) {
    $lastOk = (Get-Content -LiteralPath $statePath -Raw -Encoding UTF8).Trim()
}

if (Test-FastReady $localBuild $uiSrc $distStamp $venvOk $distOk) {
    Write-Info ""
    Write-Info "  Build $localBuild — OK, starting server..."
    Write-Info ""
    exit 0
}

Write-Info ""
Write-Info "  Build check..."
Write-Info "    Local backend : $localBuild"
Write-Info "    Local UI src  : $uiSrc"
Write-Info "    Dist stamp    : $(if ($distStamp) { $distStamp } else { '(none)' })"
if ($remoteBuild) {
    Write-Info "    GitHub        : $remoteBuild"
} else {
    Write-Info "    GitHub        : (offline or unreachable)"
}
if (-not (Test-GitInstalled)) {
    Write-Info "    Git           : (not installed — use update-zip.bat for updates)"
}

# Git pull when origin/main build differs (prefer git over raw.githubusercontent cache)
if ($remoteBuild -and $localBuild -ne $remoteBuild) {
    $gitDir = Join-Path $RepoRoot ".git"
    $canGitPull = (Test-Path -LiteralPath $gitDir) -and (Test-GitInstalled)
    if ($canGitPull) {
        Write-Info "  Updating code from GitHub (git pull)..."
        Push-Location $RepoRoot
        $pullOut = @(
            (git fetch origin 2>&1),
            (git pull --ff-only origin main 2>&1)
        ) | ForEach-Object { "$_" }
        if ($LASTEXITCODE -ne 0) {
            $pullOut += (git pull --ff-only 2>&1 | ForEach-Object { "$_" })
        }
        $pullOut | ForEach-Object { Write-Info "    $_" }
        Pop-Location
        $localBuild = Read-BuildId $mainPy 'AIDI_BUILD\s*=\s*"([^"]+)"'
        $uiSrc = Read-BuildId (Join-Path $RepoRoot "frontend\src\uiBuild.ts") 'UI_BUILD\s*=\s*"([^"]+)"'
        $remoteBuild = Get-RemoteBuildFromGit $RepoRoot
        if (-not $remoteBuild) { $remoteBuild = Get-RemoteBuildId $RepoRoot }
        Write-Info "    After pull    : $localBuild"
        if ($remoteBuild -and $remoteBuild -ne $localBuild) {
            # 로컬이 origin보다 앞선 경우(수동 복사 등) — dist만 다시 빌드하면 됨
            if ($localBuild -eq $uiSrc) {
                Write-Info "    Note: PC 소스가 GitHub 표시와 다릅니다 — 로컬 빌드로 진행합니다."
            } else {
                Show-ZipUpdateHelp $remoteBuild $localBuild
                exit 3
            }
        }
    } else {
        if ($localBuild -eq $uiSrc) {
            Write-Info "    Note: Git 없음 — 로컬 소스 기준으로 프론트 빌드합니다."
        } else {
            Show-ZipUpdateHelp $remoteBuild $localBuild
            exit 3
        }
    }
}

$py312 = Find-Python312
if (-not $py312) {
    Write-Host "ERROR: Python 3.12 required (py -3.12 or python 3.12)"
    exit 4
}

$needPip = $false
if (-not $venvOk) { $needPip = $true }
if ($lastOk -ne $localBuild) { $needPip = $true }

try {
    $venvPy = Ensure-Venv $RepoRoot $py312
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 4
}

if ($needPip) {
    try {
        Install-Pip $venvPy $RepoRoot
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)"
        exit 5
    }
}

$dataDir = Join-Path $RepoRoot "backend\data"
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }

$needFe = $false
if (-not $distOk) { $needFe = $true }
if ($uiSrc -and $uiSrc -ne $localBuild) { $needFe = $true }
if ($distStamp -ne $localBuild) { $needFe = $true }
if ($uiSrc -and $distStamp -ne $uiSrc) { $needFe = $true }

if ($needFe) {
    try {
        Build-Frontend $RepoRoot $localBuild
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)"
        exit 6
    }
}

Set-Content -LiteralPath $statePath -Value $localBuild -Encoding ascii -NoNewline
Write-Info ""
Write-Info "  Build $localBuild — ready, starting server..."
Write-Info ""
exit 0
