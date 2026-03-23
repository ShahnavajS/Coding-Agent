#Requires -Version 5.1
<#
.SYNOPSIS
    Creates (or updates) the "Production Coding Assistant" desktop shortcut.

.DESCRIPTION
    Run this once after cloning the project. It creates a .lnk shortcut on your
    Desktop that launches the app with the correct icon and working directory.
    Re-run any time to refresh the shortcut.
#>

$ErrorActionPreference = "Stop"
$ProjectRoot  = Split-Path -Parent $PSScriptRoot
$LauncherCmd  = Join-Path $ProjectRoot "Launch Production Coding Assistant.cmd"
$IconPath     = Join-Path $ProjectRoot "desktop\icons\app.ico"
$DesktopPath  = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "Production Coding Assistant.lnk"

# Fallback icon if custom one doesn't exist
if (-not (Test-Path $IconPath)) {
    $IconPath = "$env:SystemRoot\System32\imageres.dll,109"
}

$Shell    = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath       = $LauncherCmd
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.IconLocation     = $IconPath
$Shortcut.Description      = "Production Coding Assistant — AI-powered desktop IDE"
$Shortcut.WindowStyle      = 1   # Normal window
$Shortcut.Save()

Write-Host ""
Write-Host "  ✓ Desktop shortcut created:" -ForegroundColor Green
Write-Host "    $ShortcutPath" -ForegroundColor Gray
Write-Host ""
Write-Host "  Double-click it to launch the app." -ForegroundColor Cyan
Write-Host ""
