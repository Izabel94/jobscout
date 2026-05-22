@echo off
setlocal EnableDelayedExpansion

REM Launch Chrome (or Edge fallback) with DevTools remote-debugging port open
REM so jobscout scripts (bootstrap, apply worker) can attach via CDP.
REM
REM Usage:
REM   scripts\win\chrome-cdp.bat                              REM launch
REM   set JOBSCOUT_CDP_URL=http://localhost:9222
REM   set JOBSCOUT_PROFILE_LINKEDIN_URL=https://www.linkedin.com/in/...
REM
REM Close the browser window when done.

if "%PORT%"=="" set PORT=9222
if "%PROFILE_DIR%"=="" set PROFILE_DIR=%LOCALAPPDATA%\jobscout\chrome-cdp

if "%JOBSCOUT_CHROME_BIN%"=="" (
    if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
        set "JOBSCOUT_CHROME_BIN=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    ) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
        set "JOBSCOUT_CHROME_BIN=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    ) else if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
        set "JOBSCOUT_CHROME_BIN=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
    ) else (
        echo Neither Chrome nor Edge found. 1>&2
        echo Install Chrome or set JOBSCOUT_CHROME_BIN env var to your install path. 1>&2
        exit /b 1
    )
)

if not exist "%PROFILE_DIR%" mkdir "%PROFILE_DIR%"

echo Launching browser on port %PORT% with profile %PROFILE_DIR%
echo After it opens: sign into LinkedIn once, then leave the window open.
echo.

start "" "%JOBSCOUT_CHROME_BIN%" ^
    --remote-debugging-port=%PORT% ^
    --user-data-dir="%PROFILE_DIR%" ^
    --no-first-run ^
    --no-default-browser-check ^
    https://www.linkedin.com/feed/
