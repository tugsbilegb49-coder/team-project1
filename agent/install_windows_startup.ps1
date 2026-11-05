param(
    [switch]$Uninstall
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$BackendPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
$AgentScript = Join-Path $ProjectRoot "agent\main.py"
$CameraScript = Join-Path $ProjectRoot "main.py"
$BackendScript = Join-Path $ProjectRoot "backend\manage.py"
$TaskNames = @("WorkerActivityDjangoApi", "WorkerActivityDesktopAgent", "WorkerActivityCameraMonitor")

if ($Uninstall) {
    foreach ($TaskName in $TaskNames) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Write-Output "Removed $TaskName"
    }
    exit 0
}

if (-not (Test-Path $Python) -or -not (Test-Path $BackendPython)) {
    throw "Project or backend virtual environment was not found. Create both before enabling autostart."
}
if (-not (Test-Path (Join-Path $ProjectRoot "agent\.agent_tokens.json"))) {
    throw "Run 'py agent\main.py --login' before enabling autostart."
}

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

$AgentAction = New-ScheduledTaskAction -Execute $Python -Argument ('"{0}"' -f $AgentScript) -WorkingDirectory $ProjectRoot
$CameraAction = New-ScheduledTaskAction -Execute $Python -Argument ('"{0}"' -f $CameraScript) -WorkingDirectory $ProjectRoot
$BackendAction = New-ScheduledTaskAction -Execute $BackendPython -Argument ('"{0}" runserver 127.0.0.1:8000 --noreload' -f $BackendScript) -WorkingDirectory (Join-Path $ProjectRoot "backend")

Register-ScheduledTask -TaskName $TaskNames[0] -Action $BackendAction -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Register-ScheduledTask -TaskName $TaskNames[1] -Action $AgentAction -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Register-ScheduledTask -TaskName $TaskNames[2] -Action $CameraAction -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Write-Output "Installed user-level API, agent, and camera autostart tasks. They start at your next Windows sign-in."
