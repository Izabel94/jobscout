@echo off
setlocal EnableDelayedExpansion

REM Apply-queue worker for Windows Task Scheduler.
REM Triggered every 5 minutes (see JobscoutApplyWorker.xml).
REM Probes CDP Chrome on port 9222; if down + nothing pending, exits silently.
REM If down + something pending, surfaces a toast so the user knows to launch Chrome.

if "%JOBSCOUT_REPO%"=="" set JOBSCOUT_REPO=%USERPROFILE%\jobscout
if "%CDP_PORT%"=="" set CDP_PORT=9222
set "LOG_DIR=%LOCALAPPDATA%\jobscout\logs"
set "LOG_FILE=%LOG_DIR%\apply-worker.log"

set "PYTHON=%JOBSCOUT_REPO%\.venv\Scripts\python.exe"
set "DOTENV=%JOBSCOUT_REPO%\.venv\Scripts\dotenv.exe"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo. >> "%LOG_FILE%"
echo ==== %DATE% %TIME% apply-worker starting ==== >> "%LOG_FILE%"

REM Fail loud if the venv is missing, regardless of CDP state — otherwise the
REM CDP-down branch would silently exit 0 with no signal to the user.
if not exist "%PYTHON%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%JOBSCOUT_REPO%\scripts\win\notify-toast.ps1" -Title "jobscout apply-worker" -Body "venv missing: %PYTHON% — run `poetry install`"
    echo %DATE% %TIME% venv missing: %PYTHON% >> "%LOG_FILE%"
    exit /b 127
)

REM Probe CDP via PowerShell Test-NetConnection (built-in, no install).
for /f %%R in ('powershell -NoProfile -Command "(Test-NetConnection -ComputerName localhost -Port %CDP_PORT% -InformationLevel Quiet -WarningAction SilentlyContinue) -as [int]"') do set CDP_UP=%%R

if "%CDP_UP%"=="0" (
    REM Chrome is down. Check whether any apply_requests are pending.
    pushd "%JOBSCOUT_REPO%"
    for /f %%P in ('"%DOTENV%" run -- "%PYTHON%" -c "from jobscout.db import list_apply_requests; print(sum(1 for r in list_apply_requests(limit=50) if r['status'] == 'pending'))" 2^>nul') do set PENDING=%%P
    popd
    if "!PENDING!"=="" set PENDING=0
    if !PENDING! GTR 0 (
        powershell -NoProfile -ExecutionPolicy Bypass -File "%JOBSCOUT_REPO%\scripts\win\notify-toast.ps1" -Title "jobscout: !PENDING! apply request(s) waiting" -Body "Start Chrome via scripts\win\chrome-cdp.bat"
    )
    echo %DATE% %TIME% CDP Chrome down; pending=!PENDING! — exiting >> "%LOG_FILE%"
    exit /b 0
)

pushd "%JOBSCOUT_REPO%"
set "JOBSCOUT_CDP_URL=http://localhost:%CDP_PORT%"
"%DOTENV%" run -- "%PYTHON%" -m jobscout.apply.worker >> "%LOG_FILE%" 2>&1
set "STATUS=%ERRORLEVEL%"
popd

if not "%STATUS%"=="0" (
    REM Trim the last 5 log lines for the toast body.
    for /f "delims=" %%L in ('powershell -NoProfile -Command "Get-Content '%LOG_FILE%' -Tail 5 | Out-String"') do set "TAIL=!TAIL! %%L"
    powershell -NoProfile -ExecutionPolicy Bypass -File "%JOBSCOUT_REPO%\scripts\win\notify-toast.ps1" -Title "jobscout apply-worker FAILED (exit %STATUS%)" -Body "!TAIL:~0,240!"
    echo %DATE% %TIME% FAILED exit=%STATUS% >> "%LOG_FILE%"
    exit /b %STATUS%
)

echo %DATE% %TIME% OK >> "%LOG_FILE%"
