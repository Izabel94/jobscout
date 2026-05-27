param()

# Register all four jobscout Task Scheduler entries from the XML defs sitting
# next to this script. /F overwrites any pre-existing task (idempotent re-install).

$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot

$tasks = @(
    @{ Name = "Jobscout\Chrome";      Xml = "JobscoutChrome.xml" },
    @{ Name = "Jobscout\Update";      Xml = "JobscoutUpdate.xml" },
    @{ Name = "Jobscout\ApplyWorker"; Xml = "JobscoutApplyWorker.xml" },
    @{ Name = "Jobscout\Discover";    Xml = "JobscoutDiscover.xml" }
)

foreach ($t in $tasks) {
    $xmlPath = Join-Path $dir $t.Xml
    if (-not (Test-Path $xmlPath)) { throw "missing task XML: $xmlPath" }
    Write-Host "Registering $($t.Name) from $($t.Xml)"
    schtasks /Create /TN $t.Name /XML "$xmlPath" /F
    if ($LASTEXITCODE -ne 0) { throw "schtasks failed for $($t.Name) (exit $LASTEXITCODE)" }
}

Write-Host "All four tasks registered."
