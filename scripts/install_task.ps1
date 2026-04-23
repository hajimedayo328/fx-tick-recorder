# FxTickRecorder Scheduled Task installer
# Run in elevated PowerShell.
#
# Mirrors the FXBot (mentor bot) task:
#   - AtStartup trigger
#   - Runs as Administrator interactive (same session as MT5)
#   - IgnoreNew multi-instance policy
#   - Auto-restart on failure (999 times, 1 minute interval)

$TaskName = "FxTickRecorder"
$WorkingDir = "C:\tools\fx-tick-recorder"
$PythonCommand = "python -m recorder.main"

$actionParams = @{
    Execute  = "cmd"
    Argument = "/c cd /d $WorkingDir && $PythonCommand"
}
$action = New-ScheduledTaskAction @actionParams

$trigger = New-ScheduledTaskTrigger -AtStartup

$settingsParams = @{
    MultipleInstances          = "IgnoreNew"
    AllowStartIfOnBatteries    = $true
    DontStopIfGoingOnBatteries = $true
    ExecutionTimeLimit         = (New-TimeSpan -Hours 0)
    RestartInterval            = (New-TimeSpan -Minutes 1)
    RestartCount               = 999
    StartWhenAvailable         = $true
}
$settings = New-ScheduledTaskSettingsSet @settingsParams

$principalParams = @{
    UserId    = "Administrator"
    RunLevel  = "Highest"
    LogonType = "Interactive"
}
$principal = New-ScheduledTaskPrincipal @principalParams

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Task $TaskName already exists, removing first..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$registerParams = @{
    TaskName    = $TaskName
    Action      = $action
    Trigger     = $trigger
    Settings    = $settings
    Principal   = $principal
    Description = "FX tick recorder: records MT5 ticks from 30 symbols 24/7"
}
Register-ScheduledTask @registerParams | Out-Null

Write-Host ""
Write-Host "=== Task registered ==="
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State, Author | Format-Table -AutoSize
Write-Host ""
Write-Host "Management commands:"
Write-Host "  Start manually:  Start-ScheduledTask -TaskName $TaskName"
Write-Host "  Stop:            Stop-ScheduledTask -TaskName $TaskName"
Write-Host "  Check status:    Get-ScheduledTask -TaskName $TaskName"
Write-Host "  Uninstall:       Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
