@echo off
setlocal EnableExtensions DisableDelayedExpansion

pushd "%~dp0.." || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    >&2 echo Local Python environment is missing. Run install.cmd first.
    popd
    exit /b 1
)

".venv\Scripts\python.exe" main.py %*
set "WUWA_SCORE_EXIT=%errorlevel%"
popd
exit /b %WUWA_SCORE_EXIT%
