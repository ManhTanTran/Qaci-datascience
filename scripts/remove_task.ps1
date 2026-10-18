param([string]$TaskName = "WardPriceDaily")
$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "No scheduled task named '$TaskName' exists."
    return
}
if (-not ([string]$task.Description).StartsWith("WardPriceDaily daily task (")) {
    throw "Refusing to remove a task not registered by WardPriceDaily."
}
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Removed scheduled task '$TaskName'."