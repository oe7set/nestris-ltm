# Builds NestrisLTM for Windows:
#   1. admin UI + overlays (frontend/ -> src/nestris_ltm/web)
#   2. the PyInstaller folder dist/NestrisLTM
#   3. the installer dist/NestrisLTM-Setup-<version>.exe (if Inno Setup 6/7 is installed; or set $env:ISCC)
#
# Usage (from the repository root):  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
param([switch]$SkipUi, [switch]$SkipInstaller)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Select-String -Path pyproject.toml -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "NestrisLTM $version" -ForegroundColor Yellow

if (-not $SkipUi) {
    Push-Location frontend
    pnpm install --frozen-lockfile
    if ($LASTEXITCODE) { throw "pnpm install failed" }
    pnpm build
    if ($LASTEXITCODE) { throw "UI build failed" }
    Pop-Location
}

uv sync --group packaging
if ($LASTEXITCODE) { throw "uv sync failed" }
uv run --group packaging pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\nestris-ltm.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }

# Smoke test: the CLI must start and find its bundled files.
& dist\NestrisLTM\nestris-ltm.exe --version
if ($LASTEXITCODE) { throw "the built CLI does not start" }

if ($SkipInstaller) { return }
$iscc = @(
    (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source,
    $env:ISCC,
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) {
    Write-Warning "Inno Setup not found: skipping the installer (winget install JRSoftware.InnoSetup)."
    return
}
& $iscc "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Write-Host "Installer: dist\NestrisLTM-Setup-$version.exe" -ForegroundColor Green
