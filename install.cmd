@echo off
setlocal EnableExtensions DisableDelayedExpansion

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
set "WUWA_SCORE_INSTALL_EXIT=%errorlevel%"
if not "%~1"=="--no-pause" pause
exit /b %WUWA_SCORE_INSTALL_EXIT%
