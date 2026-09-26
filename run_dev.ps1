# Swing Desk - dev launcher (PowerShell 5.1+ on Windows; also runs on pwsh 7 macOS/Linux)
# Usage:  powershell -ExecutionPolicy Bypass -File .\run_dev.ps1
#         Extra args are forwarded to the app, e.g.:  .\run_dev.ps1 --self-test
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== Swing Desk dev launcher ==" -ForegroundColor Cyan

# --- sanity: make sure this is the app folder (not the handoff spec pack) ---
if (-not ((Test-Path "pyproject.toml") -and (Test-Path "src/swingdesk/main.py"))) {
    Write-Host ""
    Write-Host "ERROR: This folder does not contain the Swing Desk application." -ForegroundColor Red
    Write-Host "Expected to find: pyproject.toml and src/swingdesk/main.py next to this script."
    Write-Host "If you are inside 'SwingDesk-Next-Builder-Handoff' (the spec/asset pack),"
    Write-Host "the application is the folder you cloned/extracted from"
    Write-Host "SwingDesk-main.bundle or SwingDesk-source.zip (it contains src/, tests/, run_dev.py)."
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# --- resolve a Python 3.10+ runtime (exit code decides, never stderr text) ---
function Test-Python($exe, $arg) {
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($arg) { $out = & $exe $arg -c "import sys; print(sys.version_info >= (3, 10))" 2>$null }
        else      { $out = & $exe -c "import sys; print(sys.version_info >= (3, 10))" 2>$null }
        if ($LASTEXITCODE -eq 0 -and (@($out) -contains "True")) { return $true }
    } catch { }
    finally { $ErrorActionPreference = $oldEap }
    return $false
}

$pyExe = $null
$pyArg = ""
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in @("3.11", "3.12", "3.13", "3.14", "3.10", "3")) {
        if (Test-Python py "-$v") { $pyExe = "py"; $pyArg = "-$v"; break }
    }
}
if (-not $pyExe) {
    foreach ($c in @("python", "python3")) {
        if (Test-Python $c "") { $pyExe = $c; $pyArg = ""; break }
    }
}
if (-not $pyExe) {
    Write-Host ""
    Write-Host "ERROR: No Python 3.10+ runtime found on this machine." -ForegroundColor Red
    Write-Host ""
    Write-Host "Fix (pick one):" -ForegroundColor Yellow
    Write-Host "  winget install -e --id Python.Python.3.11" -ForegroundColor White
    Write-Host "  (or download Python 3.11 from https://www.python.org/downloads/windows/)" -ForegroundColor White
    Write-Host "Then close and reopen PowerShell and run this script again."
    Write-Host "Tip: 'py -0p' lists every Python the launcher can see."
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ("Using Python : {0} {1}" -f $pyExe, $pyArg)

# --- create/reuse the virtual environment (Windows and POSIX layouts) ---
function Get-VenvPython {
    if (Test-Path ".venv/Scripts/python.exe") { return ".\.venv\Scripts\python.exe" }
    if (Test-Path ".venv/bin/python")         { return "./.venv/bin/python" }
    return $null
}
if (-not (Get-VenvPython)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    $venvArgs = @()
    if ($pyArg) { $venvArgs += $pyArg }
    $venvArgs += @("-m", "venv", ".venv")
    & $pyExe @venvArgs
    if ($LASTEXITCODE -ne 0 -or -not (Get-VenvPython)) {
        Write-Host "ERROR: virtual environment creation failed." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

$venvPy = Get-VenvPython

# --- install dependencies when missing or when pyproject.toml changed ---
$projHash = (Get-FileHash "pyproject.toml" -Algorithm SHA256).Hash
$marker = ".venv/.deps-ok"
$needInstall = $true
if ((Test-Path $marker) -and ((Get-Content $marker -Raw).Trim() -eq $projHash)) {
    $needInstall = $false
}
if ($needInstall) {
    Write-Host "Installing dependencies (PySide6) - first run only..." -ForegroundColor Cyan
    & $venvPy -m pip install --upgrade pip -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: pip upgrade failed." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    & $venvPy -m pip install -e . -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: dependency installation failed." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Set-Content -Path $marker -Value $projHash
}

Write-Host "Launching Swing Desk..." -ForegroundColor Green
& $venvPy run_dev.py @args
exit $LASTEXITCODE
