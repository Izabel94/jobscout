param()

# Register all four jobscout Task Scheduler entries from the XML defs sitting
# next to this script. Uses Register-ScheduledTask (not schtasks /Create /XML):
# schtasks reads the XML from disk and rejects UTF-8 files with "unable to
# switch the encoding"; Register-ScheduledTask takes the XML as an in-memory
# string, so on-disk encoding doesn't matter. -Force overwrites on re-install.

$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot

$tasks = @(
    @{ Leaf = "Chrome";      Xml = "JobscoutChrome.xml" },
    @{ Leaf = "Update";      Xml = "JobscoutUpdate.xml" },
    @{ Leaf = "ApplyWorker"; Xml = "JobscoutApplyWorker.xml" },
    @{ Leaf = "Discover";    Xml = "JobscoutDiscover.xml" }
)

foreach ($t in $tasks) {
    $xmlPath = Join-Path $dir $t.Xml
    if (-not (Test-Path $xmlPath)) { throw "missing task XML: $xmlPath" }
    Write-Host "Registering Jobscout\$($t.Leaf) from $($t.Xml)"
    $xml = Get-Content -Path $xmlPath -Raw
    Register-ScheduledTask -TaskName $t.Leaf -TaskPath "\Jobscout\" -Xml $xml -Force | Out-Null
}

Write-Host "All four tasks registered."
