@echo off
setlocal EnableDelayedExpansion

REM Launch Chrome (or Edge fallback) with DevTools remote-debugging port open
REM so jobscout scripts (bootstrap, apply worker) can attach via CDP.
REM
REM Usage:
REM   scripts\win\chrome-cdp.bat                              REM launch
REM   set JOBSCOUT_CDP_URL=http://localhost:9223
REM   set JOBSCOUT_PROFILE_LINKEDIN_URL=https://www.linkedin.com/in/...
REM
REM Close the browser window when done.

if "%PORT%"=="" set PORT=9223
if "%PROFILE_DIR%"=="" set PROFILE_DIR=%LOCALAPPDATA%\jobscout\chrome-cdp

REM If the debug port is already bound, Chrome is healthy — reuse it instead of
REM launching a second window (apply-worker.bat call's this on-demand and would
REM otherwise spawn a duplicate every tick).
for /f %%R in ('powershell -NoProfile -Command "(Test-NetConnection -ComputerName localhost -Port %PORT% -InformationLevel Quiet -WarningAction SilentlyContinue) -as [int]"') do set PORT_UP=%%R
if "%PORT_UP%"=="1" (
    echo Apply browser already running on port %PORT% - reusing it.
    exit /b 0
)

REM Honor the browser chosen at install time (install-chrome.ps1 writes "chrome"
REM or "msedge" here when Chrome install fell back to Edge).
set "BROWSER_FILE=%LOCALAPPDATA%\jobscout\browser.txt"
if "%JOBSCOUT_CHROME_BIN%"=="" if exist "%BROWSER_FILE%" (
    set /p CHOSEN_BROWSER=<"%BROWSER_FILE%"
    if "!CHOSEN_BROWSER!"=="msedge" (
        if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
            set "JOBSCOUT_CHROME_BIN=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
        ) else if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
            set "JOBSCOUT_CHROME_BIN=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
        )
    )
)

if "%JOBSCOUT_CHROME_BIN%"=="" (
    if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
        set "JOBSCOUT_CHROME_BIN=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    ) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
        set "JOBSCOUT_CHROME_BIN=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    ) else if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
        set "JOBSCOUT_CHROME_BIN=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
    ) else if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
        set "JOBSCOUT_CHROME_BIN=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
    ) else (
        echo Neither Chrome nor Edge found. 1>&2
        echo Install Chrome or set JOBSCOUT_CHROME_BIN env var to your install path. 1>&2
        exit /b 1
    )
)

if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"

REM Self-recover from a stale apply-Chrome. The port is down (checked above) yet
REM a crashed/half-dead Chrome may still hold this profile, blocking the debug
REM port from binding on the next launch. Kill ONLY browsers on the jobscout
REM profile (matched by --user-data-dir on the command line) so the user's normal
REM Chrome is never touched, then clear the leftover Singleton locks.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'chrome.exe' -or $_.Name -eq 'msedge.exe') -and $_.CommandLine -like '*jobscout\chrome-cdp*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>nul
del /q "%PROFILE_DIR%\SingletonLock" 2>nul
del /q "%PROFILE_DIR%\SingletonCookie" 2>nul
del /q "%PROFILE_DIR%\SingletonSocket" 2>nul

echo Launching browser on port %PORT% with profile %PROFILE_DIR%
echo After it opens: sign into LinkedIn once, then leave the window open.
echo.

start "" "%JOBSCOUT_CHROME_BIN%" ^
    --remote-debugging-port=%PORT% ^
    --user-data-dir="%PROFILE_DIR%" ^
    --no-first-run ^
    --no-default-browser-check ^
    https://www.linkedin.com/feed/
