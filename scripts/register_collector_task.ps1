param(
    [switch]$PilotPassed,
    [switch]$Register
)

$ErrorActionPreference = 'Stop'
if (-not $PilotPassed -or -not $Register) {
    throw 'Task Scheduler registration is disabled by default. After a successful limited pilot and explicit approval, rerun with both -PilotPassed and -Register.'
}
if ((Get-TimeZone).Id -ne 'SE Asia Standard Time') {
    throw "Set Windows time zone to 'SE Asia Standard Time' before registering the 08:00 Vietnam-time task."
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $PSScriptRoot 'run_daily_collection.ps1'
if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Collection runner not found: $Runner"
}
$TaskName = 'WardPriceDaily-Collector'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "Task '$TaskName' already exists. Inspect or remove it manually; this script will not overwrite it."
}

$PowerShell = Join-Path $PSHOME 'powershell.exe'
$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`""
$Trigger = New-ScheduledTaskTrigger -Daily -At '08:00'
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType InteractiveToken -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DisallowStartIfOnBatteries:$false -StopIfGoingOnBatteries:$false -ExecutionTimeLimit (New-TimeSpan -Hours 4)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "WardPriceDaily public-source collection at 08:00 local time. Sources remain subject to the approved source registry." | Out-Null
Write-Output "Registered '$TaskName' for 08:00 daily. No task was started immediately."
