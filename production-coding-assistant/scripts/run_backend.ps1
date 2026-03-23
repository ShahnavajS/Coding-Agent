#Requires -Version 5.1
# Run the Python backend in the foreground (for development / debugging).
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python      = Join-Path $ProjectRoot "..\\.venv\Scripts\python.exe"
$Entry       = Join-Path $ProjectRoot "backend\server.py"

if (-not (Test-Path $Python)) {
    Write-Host "ERROR: Python venv not found at $Python" -ForegroundColor Red
    Write-Host "Create it with:  python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting backend on http://localhost:5000 ..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "backend")
& $Python $Entry
