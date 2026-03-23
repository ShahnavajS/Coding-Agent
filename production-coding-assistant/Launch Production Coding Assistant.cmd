@echo off
:: Production Coding Assistant — Desktop Launcher
:: Double-click this file or use the desktop shortcut to start the app.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch_app.ps1"
endlocal
