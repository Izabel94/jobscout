@echo off
setlocal EnableDelayedExpansion

REM Jobscout uninstall. Removes the four Task Scheduler entries and the desktop
REM shortcut, then optionally the repo + state dirs. Run from anywhere.

set "JOBSCOUT_REPO=%USERPROFILE%\jobscout"
set "STATE_DIR=%LOCALAPPDATA%\jobscout"

echo Removing jobscout scheduled tasks...
schtasks /Delete /TN "Jobscout\Chrome"      /F 2>nul
schtasks /Delete /TN "Jobscout\Update"      /F 2>nul
schtasks /Delete /TN "Jobscout\ApplyWorker" /F 2>nul
schtasks /Delete /TN "Jobscout\Discover"    /F 2>nul

set "SHORTCUT=%USERPROFILE%\Desktop\Jobscout Dashboard.url"
if exist "%SHORTCUT%" del /F /Q "%SHORTCUT%"

echo.
set /p REMOVE="Also delete the jobscout program files and logs? [Y/N] "
if /i "%REMOVE%"=="Y" (
    if exist "%JOBSCOUT_REPO%" rmdir /S /Q "%JOBSCOUT_REPO%"
    if exist "%STATE_DIR%"     rmdir /S /Q "%STATE_DIR%"
    echo Removed %JOBSCOUT_REPO% and %STATE_DIR%.
) else (
    echo Left program files in place at %JOBSCOUT_REPO%.
)

echo.
echo Uninstall complete.
pause
