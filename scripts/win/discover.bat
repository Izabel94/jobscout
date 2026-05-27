@echo off
setlocal EnableDelayedExpansion

REM Daily discovery - scrapes LinkedIn + Indeed, writes new listings to Supabase.
REM Triggered by Task Scheduler at 10:30 Berlin time (see JobscoutDiscover.xml).

if "%JOBSCOUT_REPO%"=="" set JOBSCOUT_REPO=%USERPROFILE%\jobscout
set "LOG_DIR=%LOCALAPPDATA%\jobscout\logs"
set "LOG_FILE=%LOG_DIR%\discover.log"

set "PYTHON=%JOBSCOUT_REPO%\.venv\Scripts\python.exe"
set "DOTENV=%JOBSCOUT_REPO%\.venv\Scripts\dotenv.exe"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo. >> "%LOG_FILE%"
echo ==== %DATE% %TIME% discover starting ==== >> "%LOG_FILE%"

if not exist "%PYTHON%" (
    echo venv missing: %PYTHON% - run `poetry install` >> "%LOG_FILE%"
    exit /b 127
)

pushd "%JOBSCOUT_REPO%"
"%DOTENV%" run -- "%PYTHON%" -m jobscout.discover >> "%LOG_FILE%" 2>&1
set "STATUS=%ERRORLEVEL%"
popd

if not "%STATUS%"=="0" (
    echo %DATE% %TIME% FAILED exit=%STATUS% >> "%LOG_FILE%"
    powershell -NoProfile -ExecutionPolicy Bypass -File "%JOBSCOUT_REPO%\scripts\win\notify-toast.ps1" -Title "jobscout discover FAILED" -Body "exit %STATUS%; see %LOG_FILE%"
    exit /b %STATUS%
)

echo %DATE% %TIME% OK >> "%LOG_FILE%"
