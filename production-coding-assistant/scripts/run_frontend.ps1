#Requires -Version 5.1
# Run the Vite frontend dev server.
$ErrorActionPreference = "Stop"
$FrontendDir = Join-Path (Split-Path -Parent $PSScriptRoot) "frontend"

$npm = (Get-Command "npm" -ErrorAction SilentlyContinue)?.Source
if (-not $npm) {
    # Volta fallback
    $volta = "$env:APPDATA\Volta\bin\npm.cmd"
    $npm   = if (Test-Path $volta) { $volta } else { $null }
}
if (-not $npm) {
    Write-Host "ERROR: npm not found. Install Node.js or Volta." -ForegroundColor Red
    exit 1
}

Write-Host "Starting Vite dev server on http://localhost:5173 ..." -ForegroundColor Cyan
Set-Location $FrontendDir
& $npm run dev
