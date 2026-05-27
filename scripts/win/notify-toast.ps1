param(
    [Parameter(Mandatory=$true)][string]$Title,
    [Parameter(Mandatory=$true)][string]$Body
)

try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $xml = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>$([System.Security.SecurityElement]::Escape($Title))</text>
      <text>$([System.Security.SecurityElement]::Escape($Body))</text>
    </binding>
  </visual>
</toast>
"@

    $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
    $doc.LoadXml($xml)
    $toast = New-Object Windows.UI.Notifications.ToastNotification($doc)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("jobscout").Show($toast)
} catch {
    $logDir = Join-Path $env:LOCALAPPDATA "jobscout\logs"
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
    $line = "{0} [notify-fallback] {1} - {2}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"), $Title, $Body
    Add-Content -Path (Join-Path $logDir "notify.log") -Value $line
}
