# FxTickSummaryWeekly Scheduled Task installer
# Generates a weekly summary report every Monday early morning.
# Run in elevated PowerShell.

$TaskName = "FxTickSummaryWeekly"
$WorkingDir = "C:\tools\fx-tick-recorder"
$PythonCommand = "python -m recorder.summary"

$actionParams = @{
    Execute  = "cmd"
    Argument = "/c cd /d $WorkingDir && $PythonCommand"
}
$action = New-ScheduledTaskAction @actionParams

# Trigger: every Monday at 06:00 local time
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "06:00"

$settingsParams = @{
    MultipleInstances          = "IgnoreNew"
    AllowStartIfOnBatteries    = $true
    DontStopIfGoingOnBatteries = $true
    ExecutionTimeLimit         = (New-TimeSpan -Minutes 30)
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
    Description = "FX tick recorder: weekly summary report (Mondays 06:00)"
}
Register-ScheduledTask @registerParams | Out-Null

Write-Host ""
Write-Host "=== Task registered ==="
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State | Format-Table -AutoSize
Write-Host ""
Write-Host "Management commands:"
Write-Host "  Run now manually:  Start-ScheduledTask -TaskName $TaskName"
Write-Host "  Check status:      Get-ScheduledTask -TaskName $TaskName"
Write-Host "  Uninstall:         Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
Write-Host ""
Write-Host "Output will be written to: C:\TickData\_logs\weekly_summary_YYYY-WNN.md"
