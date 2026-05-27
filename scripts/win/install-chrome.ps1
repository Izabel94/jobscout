param()

# Ensure Google Chrome is present for the CDP apply flow. If absent, silent-install
# Google's Enterprise MSI. If that fails, fall back to preinstalled Edge (Chromium-based,
# same CDP code path). Writes the chosen browser to %LOCALAPPDATA%\jobscout\browser.txt,
# which chrome-cdp.bat reads to pick the binary.

$ErrorActionPreference = "Stop"

$stateDir = Join-Path $env:LOCALAPPDATA "jobscout"
if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Path $stateDir | Out-Null }
$browserFile = Join-Path $stateDir "browser.txt"

# File-path probe is more reliable than the BLBeacon registry key, which is only
# written after Chrome's first launch (not at install time).
$chromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
)
$chromeExe = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($chromeExe) {
    Set-Content -Path $browserFile -Value "chrome"
    Write-Host "Chrome already present: $chromeExe"
    exit 0
}

$msi = Join-Path $env:TEMP "GoogleChromeEnterprise64.msi"
try {
    Write-Host "Chrome not found - downloading Enterprise MSI..."
    Invoke-WebRequest -Uri "https://dl.google.com/chrome/install/GoogleChromeStandaloneEnterprise64.msi" `
        -OutFile $msi -UseBasicParsing
    $rc = (Start-Process msiexec -ArgumentList "/i `"$msi`" /quiet /norestart NOGOOGLEUPDATESERVICE=1" -Wait -PassThru).ExitCode
    if ($rc -ne 0) { throw "msiexec exit $rc" }
    Set-Content -Path $browserFile -Value "chrome"
    Write-Host "Chrome installed."
} catch {
    Write-Warning "Chrome install failed: $_ - falling back to Edge"
    Set-Content -Path $browserFile -Value "msedge"
} finally {
    if (Test-Path $msi) { Remove-Item $msi -Force -ErrorAction SilentlyContinue }
}
