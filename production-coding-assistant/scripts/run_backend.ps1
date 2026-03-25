#Requires -Version 5.1
# Run the Python backend in the foreground (for development / debugging).
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# .venv can be inside the project OR one level up (at the Coding agent root)
$candidates = @(
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
    (Join-Path (Split-Path -Parent $ProjectRoot) ".venv\Scripts\python.exe")
)
$Python = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $Python) {
    Write-Host "ERROR: Python venv not found. Checked:" -ForegroundColor Red
    $candidates | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Write-Host "Create it with:  python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

$Entry = Join-Path $ProjectRoot "backend\server.py"
Write-Host "Using Python: $Python" -ForegroundColor Cyan
Write-Host "Starting backend on http://localhost:5000 ..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "backend")
& $Python $Entry
