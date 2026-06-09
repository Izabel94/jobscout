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
    echo %DATE% %TIME% MinGit missing at %GIT% - bootstrap incomplete >> "%LOG_FILE%"
    exit /b 127
)
if not exist "%SSH_KEY%" (
    echo %DATE% %TIME% deploy key missing at %SSH_KEY% - operator must drop it via RDP >> "%LOG_FILE%"
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
    echo %DATE% %TIME% requirements.win.txt changed - reinstalling deps >> "%LOG_FILE%"
    "%PYTHON%" -m pip install -r "%JOBSCOUT_REPO%\requirements.win.txt" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo %DATE% %TIME% pip install FAILED >> "%LOG_FILE%"
        popd
        exit /b 1
    )
    > "%HASH_FILE%" echo %REQHASH%
)

REM Re-register the scheduled tasks when their XML defs change (new task, or a
REM changed interval/timeout). Needs the elevated Update task (HighestAvailable);
REM Register-ScheduledTask -Force is idempotent. Detect change via the joined
REM SHA256 of the task XMLs.
set "TASKHASH_FILE=%STATE_DIR%\taskhash.txt"
set "TASKHASH="
for /f "delims=" %%H in ('powershell -NoProfile -Command "(Get-ChildItem '%JOBSCOUT_REPO%\scripts\win\Jobscout*.xml' ^| Sort-Object Name ^| Get-FileHash -Algorithm SHA256).Hash -join ','"') do set "TASKHASH=%%H"
set "LASTTASKHASH="
if exist "%TASKHASH_FILE%" set /p LASTTASKHASH=<"%TASKHASH_FILE%"
if not "%TASKHASH%"=="%LASTTASKHASH%" (
    echo %DATE% %TIME% task XMLs changed - re-registering scheduled tasks >> "%LOG_FILE%"
    powershell -NoProfile -ExecutionPolicy Bypass -File "%JOBSCOUT_REPO%\scripts\win\install-tasks.ps1" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo %DATE% %TIME% task re-registration FAILED ^(needs elevation^) >> "%LOG_FILE%"
    ) else (
        > "%TASKHASH_FILE%" echo %TASKHASH%
    )
)

popd
echo %DATE% %TIME% OK >> "%LOG_FILE%"
