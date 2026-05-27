@echo off
setlocal EnableDelayedExpansion

REM Jobscout one-time bootstrap. Julian double-clicks this after extracting the ZIP.
REM Idempotent — safe to re-run. Lays down the repo, a Python venv, Playwright's
REM chromium, Chrome (Edge fallback), and the four Task Scheduler entries.
REM
REM The ZIP ships the repo with .git so no private-repo clone (and no deploy key)
REM is needed at install time. The deploy key is dropped by the operator via RDP
REM afterwards; it's only used by the hourly update.bat for `git fetch`.
REM
REM Vendor files sit next to this script at the ZIP root (%~dp0):
REM   jobscout-repo\           full repo clone (origin remote = SSH URL)
REM   python-3.13-amd64.exe    python.org user-scope installer
REM   MinGit.zip               portable git for the updater

set "HERE=%~dp0"
set "JOBSCOUT_REPO=%USERPROFILE%\jobscout"
set "STATE_DIR=%LOCALAPPDATA%\jobscout"
set "LOG_DIR=%STATE_DIR%\logs"
set "LOG_FILE=%LOG_DIR%\install.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo ==== %DATE% %TIME% install starting ==== >> "%LOG_FILE%"

call :log "Setting up jobscout. This takes a few minutes — please don't close this window."

REM --- 1. Lay down the repo --------------------------------------------------
if not exist "%JOBSCOUT_REPO%\.git" (
    call :log "Copying jobscout files..."
    robocopy "%HERE%jobscout-repo" "%JOBSCOUT_REPO%" /E /NFL /NDL /NJH /NJS /NP >> "%LOG_FILE%" 2>&1
)

REM --- 2. Python (user-scope, no admin) --------------------------------------
REM Detect an existing Python 3.13 first (py launcher, else a 3.13 on PATH) so we
REM never trigger the installer's repair/modify dialog on a machine that already
REM has Python. Only install if genuinely absent, and use /passive (visible
REM progress) instead of /quiet, which can hang silently behind a dialog.
set "PYLAUNCH="
py -3.13 --version >nul 2>&1 && set "PYLAUNCH=py -3.13"
if not defined PYLAUNCH (
    python --version 2>&1 | findstr /b "Python 3.13" >nul && set "PYLAUNCH=python"
)
if not defined PYLAUNCH (
    call :log "Installing Python 3.13..."
    start /wait "" "%HERE%python-3.13-amd64.exe" /passive InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
    set "PYLAUNCH=py -3.13"
)

REM --- 3. MinGit (for the hourly updater) ------------------------------------
if not exist "%STATE_DIR%\mingit\cmd\git.exe" (
    call :log "Unpacking git..."
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Force '%HERE%MinGit.zip' '%STATE_DIR%\mingit'" >> "%LOG_FILE%" 2>&1
)

REM --- 4. venv + deps --------------------------------------------------------
set "PYTHON=%JOBSCOUT_REPO%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    call :log "Creating Python environment..."
    %PYLAUNCH% -m venv "%JOBSCOUT_REPO%\.venv" >> "%LOG_FILE%" 2>&1
)
call :log "Installing dependencies (this is the slow part)..."
"%PYTHON%" -m pip install --upgrade pip >> "%LOG_FILE%" 2>&1
call :pip_retry

REM --- 5. Playwright chromium ------------------------------------------------
call :log "Downloading browser engine..."
"%PYTHON%" -m playwright install chromium >> "%LOG_FILE%" 2>&1

REM --- 6. Chrome (Edge fallback) ---------------------------------------------
call :log "Checking for Chrome..."
powershell -NoProfile -ExecutionPolicy Bypass -File "%JOBSCOUT_REPO%\scripts\win\install-chrome.ps1" >> "%LOG_FILE%" 2>&1

REM --- 7. .env placeholder (operator pastes real values via RDP) -------------
if not exist "%JOBSCOUT_REPO%\.env" (
    copy /Y "%JOBSCOUT_REPO%\scripts\win\.env.example" "%JOBSCOUT_REPO%\.env" >> "%LOG_FILE%" 2>&1
)

REM --- 8. Task Scheduler entries ---------------------------------------------
call :log "Registering scheduled tasks..."
powershell -NoProfile -ExecutionPolicy Bypass -File "%JOBSCOUT_REPO%\scripts\win\install-tasks.ps1" >> "%LOG_FILE%" 2>&1

REM --- 9. Start Chrome now so the first apply works before any reboot --------
schtasks /Run /TN "Jobscout\Chrome" >> "%LOG_FILE%" 2>&1

REM --- 10. Desktop shortcut to the dashboard --------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'Jobscout Dashboard.url'));$s.TargetPath='https://jobscout-julian.streamlit.app/';$s.Save()" >> "%LOG_FILE%" 2>&1

call :log ""
call :log "Install complete. Please text Izabel — she'll finish the setup remotely."
echo %DATE% %TIME% install done >> "%LOG_FILE%"
echo.
pause
exit /b 0

REM --- helpers ---------------------------------------------------------------
:log
echo %~1
echo %DATE% %TIME% %~1 >> "%LOG_FILE%"
exit /b 0

:pip_retry
REM pip install with 3 retries — chromium/wheel downloads can blip on flaky wifi.
set /a _try=0
:pip_loop
set /a _try+=1
"%PYTHON%" -m pip install -r "%JOBSCOUT_REPO%\requirements.win.txt" >> "%LOG_FILE%" 2>&1
if not errorlevel 1 exit /b 0
if %_try% GEQ 3 (
    call :log "Dependency install failed after 3 tries — check wifi, then re-run install."
    exit /b 1
)
call :log "Dependency install hiccup — retrying (%_try%/3)..."
timeout /t 5 /nobreak >nul
goto :pip_loop
