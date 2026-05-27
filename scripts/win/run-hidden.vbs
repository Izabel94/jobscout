' Runs a batch file with no visible console window. Task Scheduler actions that
' invoke a .bat directly flash a console every run (every minute for the apply
' worker); routing them through this launcher keeps them silent. Chrome and
' other GUI processes the .bat starts still appear normally - only the batch
' console itself is hidden.
'
' Usage: wscript.exe run-hidden.vbs "C:\path\to\script.bat"
Set sh = CreateObject("WScript.Shell")
sh.Run "cmd /c """ & WScript.Arguments(0) & """", 0, False
