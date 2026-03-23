#Requires -Version 5.1
<#
.SYNOPSIS
    Production Coding Assistant — smart launcher.

.DESCRIPTION
    Launch priority:
      1. Packaged Electron .exe  (fastest, no dependencies needed at runtime)
      2. Electron dev mode        (npm run electron:dev — builds & hot-reloads)
      3. Browser dev mode         (starts Python backend + Vite frontend, opens browser)

    Set $LaunchMode below to force a specific mode, or leave as "auto".
#>

$LaunchMode   = "auto"          # "auto" | "packaged" | "electron-dev" | "browser-dev"
$FrontendPort = 5173
$BackendPort  = 5000
$BackendWaitSeconds = 12        # how long to wait for backend to become ready

# ── Resolve paths ───────────────────────────────────────────────────
$ProjectRoot  = Split-Path -Parent $PSScriptRoot
$PackagedExe  = Join-Path $ProjectRoot "out\Production Coding Assistant-win32-x64\production-coding-assistant.exe"
$VenvPython   = Join-Path $ProjectRoot "..\\.venv\Scripts\python.exe"
$BackendEntry = Join-Path $ProjectRoot "backend\server.py"
$FrontendDir  = Join-Path $ProjectRoot "frontend"

# Volta/nvm-aware npm resolution
function Find-Npm {
    $candidates = @(
        (Get-Command "npm" -ErrorAction SilentlyContinue)?.Source,
        "$env:APPDATA\Volta\bin\npm.cmd",
        "$env:LOCALAPPDATA\Volta\tools\image\node\*\npm.cmd" | Resolve-Path -ErrorAction SilentlyContinue | Select-Object -Last 1 -ExpandProperty Path,
        "C:\Program Files\nodejs\npm.cmd"
    ) | Where-Object { $_ -and (Test-Path $_) }
    return $candidates | Select-Object -First 1
}

# ── Helpers ──────────────────────────────────────────────────────────
function Write-Banner {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║   Production Coding Assistant            ║" -ForegroundColor Cyan
    Write-Host "  ║   AI-powered desktop IDE                 ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step([string]$msg) {
    Write-Host "  → $msg" -ForegroundColor White
}

function Write-Ok([string]$msg) {
    Write-Host "  ✓ $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "  ⚠ $msg" -ForegroundColor Yellow
}

function Write-Fail([string]$msg) {
    Write-Host "  ✗ $msg" -ForegroundColor Red
}

function Wait-Backend([int]$port, [int]$timeoutSec) {
    Write-Step "Waiting for backend on :$port…"
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$port/api/health" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

# ── Mode: packaged exe ───────────────────────────────────────────────
function Launch-Packaged {
    if (-not (Test-Path $PackagedExe)) { return $false }
    Write-Ok "Packaged app found — launching…"
    Start-Process -FilePath $PackagedExe -WorkingDirectory (Split-Path -Parent $PackagedExe)
    return $true
}

# ── Mode: Electron dev ───────────────────────────────────────────────
function Launch-ElectronDev {
    $npm = Find-Npm
    if (-not $npm) {
        Write-Warn "npm not found — cannot launch Electron dev mode"
        return $false
    }
    $nodeModules = Join-Path $ProjectRoot "node_modules"
    if (-not (Test-Path $nodeModules)) {
        Write-Step "Installing root dependencies (electron-forge)…"
        & $npm install --prefix $ProjectRoot
    }
    Write-Ok "Starting Electron (dev mode)…"
    Write-Warn "Press Ctrl+C in this window to stop."
    Set-Location $ProjectRoot
    & $npm run electron:dev
    return $true
}

# ── Mode: browser dev (backend + Vite) ──────────────────────────────
function Launch-BrowserDev {
    $npm = Find-Npm

    # --- Backend ---
    if (-not (Test-Path $VenvPython)) {
        Write-Fail "Python venv not found at: $VenvPython"
        Write-Warn "Run:  python -m venv .venv  then  .venv\Scripts\pip install -r requirements.txt"
        return $false
    }
    Write-Step "Starting Python backend (port $BackendPort)…"
    $backendJob = Start-Process -FilePath $VenvPython `
        -ArgumentList $BackendEntry `
        -WorkingDirectory (Join-Path $ProjectRoot "backend") `
        -PassThru -WindowStyle Hidden

    $ready = Wait-Backend -port $BackendPort -timeoutSec $BackendWaitSeconds
    if ($ready) {
        Write-Ok "Backend ready"
    } else {
        Write-Warn "Backend did not respond in time — continuing anyway"
    }

    # --- Frontend ---
    if (-not $npm) {
        Write-Warn "npm not found — open http://localhost:$BackendPort manually"
        Write-Warn "Backend PID: $($backendJob.Id)"
        return $true
    }

    $frontendModules = Join-Path $FrontendDir "node_modules"
    if (-not (Test-Path $frontendModules)) {
        Write-Step "Installing frontend dependencies…"
        & $npm install --prefix $FrontendDir
    }

    Write-Step "Starting Vite dev server (port $FrontendPort)…"
    $viteJob = Start-Process -FilePath $npm `
        -ArgumentList "run", "dev" `
        -WorkingDirectory $FrontendDir `
        -PassThru -WindowStyle Hidden

    # Wait a moment then open the browser
    Start-Sleep -Seconds 3
    Write-Ok "Opening browser → http://localhost:$FrontendPort"
    Start-Process "http://localhost:$FrontendPort"

    Write-Host ""
    Write-Host "  Running processes:" -ForegroundColor Cyan
    Write-Host "    Backend  PID $($backendJob.Id)   http://localhost:$BackendPort" -ForegroundColor Gray
    Write-Host "    Frontend PID $($viteJob.Id)   http://localhost:$FrontendPort" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Press Enter to stop both servers and exit." -ForegroundColor Yellow
    $null = Read-Host

    Stop-Process -Id $backendJob.Id  -ErrorAction SilentlyContinue
    Stop-Process -Id $viteJob.Id     -ErrorAction SilentlyContinue
    Write-Ok "Stopped."
    return $true
}

# ── Entry point ──────────────────────────────────────────────────────
$ErrorActionPreference = "Stop"
Write-Banner

switch ($LaunchMode) {
    "packaged"     { if (-not (Launch-Packaged))     { Write-Fail "Packaged exe not found. Build with: npm run electron:make" } }
    "electron-dev" { Launch-ElectronDev | Out-Null }
    "browser-dev"  { Launch-BrowserDev  | Out-Null }
    default {
        Write-Step "Mode: auto — detecting best launch option…"
        if (Launch-Packaged)     { exit 0 }
        Write-Warn "No packaged build found. Falling back to browser dev mode."
        Write-Warn "(Run 'npm run electron:make' to build a packaged .exe)"
        Write-Host ""
        Launch-BrowserDev | Out-Null
    }
}
