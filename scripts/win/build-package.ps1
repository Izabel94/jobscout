param(
    [string]$PythonVersion = "3.13.3",
    [string]$MinGitVersion = "2.49.0.windows.1",
    [string]$SshRemote = "git@github.com:Izabel94/jobscout.git"
)

# Operator-side build. Run on the physical Windows laptop (Briefcase research
# confirmed no cross-build from macOS, and the same holds for a Python venv:
# Windows wheels are platform-specific). Produces dist\jobscout-windows-<date>.zip
# containing the repo (with .git, SSH remote preset), a python.org user-scope
# installer, MinGit, and the bootstrap scripts. Julian double-clicks install.bat
# inside the extracted ZIP.

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$cache    = Join-Path $env:LOCALAPPDATA "jobscout-build-cache"
$staging  = Join-Path $env:TEMP ("jobscout-pkg-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$distDir  = Join-Path $repoRoot "dist"
New-Item -ItemType Directory -Force -Path $cache, $staging, $distDir | Out-Null

# --- 1. python.org user-scope installer ------------------------------------
$pyExe = Join-Path $cache "python-$PythonVersion-amd64.exe"
if (-not (Test-Path $pyExe)) {
    $pyUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
    Write-Host "Downloading Python $PythonVersion..."
    Invoke-WebRequest -Uri $pyUrl -OutFile $pyExe -UseBasicParsing
}

# --- 2. MinGit (portable git for the updater) ------------------------------
$minGitZip = Join-Path $cache "MinGit-$MinGitVersion.zip"
if (-not (Test-Path $minGitZip)) {
    $tag = "v" + ($MinGitVersion -replace '\.windows\.', '.windows.')
    $mgUrl = "https://github.com/git-for-windows/git/releases/download/$tag/MinGit-$MinGitVersion-64-bit.zip"
    Write-Host "Downloading MinGit $MinGitVersion..."
    Invoke-WebRequest -Uri $mgUrl -OutFile $minGitZip -UseBasicParsing
}

# --- 3. Clone the repo into staging, point origin at the SSH URL -----------
$repoStage = Join-Path $staging "jobscout-repo"
Write-Host "Cloning repo into staging..."
git clone "$repoRoot" "$repoStage" | Out-Null
git -C $repoStage remote set-url origin $SshRemote
# Make sure the bundled clone tracks origin/main so update.bat can fast-forward.
git -C $repoStage fetch origin main 2>$null
git -C $repoStage branch --set-upstream-to=origin/main main 2>$null

# --- 4. Stage vendor files + bootstrap entry at ZIP root -------------------
Copy-Item $pyExe     (Join-Path $staging "python-3.13-amd64.exe")
Copy-Item $minGitZip (Join-Path $staging "MinGit.zip")
Copy-Item (Join-Path $repoStage "scripts\win\install.bat")   $staging
Copy-Item (Join-Path $repoStage "scripts\win\uninstall.bat") $staging
Copy-Item (Join-Path $repoStage "scripts\win\INSTALL.md")    $staging

# --- 5. Zip it -------------------------------------------------------------
$zip = Join-Path $distDir ("jobscout-windows-" + (Get-Date -Format "yyyyMMdd") + ".zip")
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host "Compressing..."
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zip
Remove-Item $staging -Recurse -Force

Write-Host ""
Write-Host "Built: $zip"
Write-Host "Drop it in the Syncthing folder shared with Julian, then walk him through INSTALL.md."
