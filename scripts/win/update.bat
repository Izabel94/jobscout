@echo off
setlocal EnableDelayedExpansion

REM Hourly auto-updater (Task Scheduler: Jobscout\Update). Decoupled from the
REM apply worker so a code update never races a running worker.
REM
REM   git fetch origin main  +  git reset --hard origin/main
REM
REM reset --hard (not pull --ff-only): the tree is read-only-by-contract on the
REM end-user machine. A crash or AV writing into it creates local changes that
REM would silently block --ff-only, stranding the user on stale code. Nuke drift.
REM
REM Auth: read-only SSH deploy key via vendored MinGit's bundled ssh,
REM non-interactive so the unattended task fails cleanly instead of hanging.

if "%JOBSCOUT_REPO%"=="" set "JOBSCOUT_REPO=%USERPROFILE%\jobscout"
set "STATE_DIR=%LOCALAPPDATA%\jobscout"
set "LOG_DIR=%STATE_DIR%\logs"
set "LOG_FILE=%LOG_DIR%\update.log"
set "HASH_FILE=%STATE_DIR%\reqhash.txt"
set "GIT=%STATE_DIR%\mingit\cmd\git.exe"
set "SSH_KEY=%USERPROFILE%\.ssh\jobscout_deploy"
set "PYTHON=%JOBSCOUT_REPO%\.venv\Scripts\python.exe"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo. >> "%LOG_FILE%"
echo ==== %DATE% %TIME% update starting ==== >> "%LOG_FILE%"

if not exist "%GIT%" (
    echo %DATE% %TIME% MinGit missing at %GIT% — bootstrap incomplete >> "%LOG_FILE%"
    exit /b 127
)
if not exist "%SSH_KEY%" (
    echo %DATE% %TIME% deploy key missing at %SSH_KEY% — operator must drop it via RDP >> "%LOG_FILE%"
    exit /b 1
)

set "GIT_SSH_COMMAND=ssh -i \"%SSH_KEY%\" -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

pushd "%JOBSCOUT_REPO%"

"%GIT%" -c credential.interactive=false fetch origin main >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo %DATE% %TIME% fetch FAILED >> "%LOG_FILE%"
    popd
    exit /b 1
)

"%GIT%" reset --hard origin/main >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo %DATE% %TIME% reset FAILED >> "%LOG_FILE%"
    popd
    exit /b 1
)

REM Re-install deps only when requirements.win.txt changed since the last run.
set "REQHASH="
for /f %%H in ('certutil -hashfile "%JOBSCOUT_REPO%\requirements.win.txt" SHA256 ^| findstr /r "^[0-9a-f][0-9a-f]"') do if not defined REQHASH set "REQHASH=%%H"
set "LASTHASH="
if exist "%HASH_FILE%" set /p LASTHASH=<"%HASH_FILE%"

if not "%REQHASH%"=="%LASTHASH%" (
    echo %DATE% %TIME% requirements.win.txt changed — reinstalling deps >> "%LOG_FILE%"
    "%PYTHON%" -m pip install -r "%JOBSCOUT_REPO%\requirements.win.txt" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo %DATE% %TIME% pip install FAILED >> "%LOG_FILE%"
        popd
        exit /b 1
    )
    > "%HASH_FILE%" echo %REQHASH%
)

popd
echo %DATE% %TIME% OK >> "%LOG_FILE%"
