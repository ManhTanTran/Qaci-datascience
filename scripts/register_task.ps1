param(
    [string]$TaskName = "WardPriceDaily",
    [string]$Time = "08:17",
    [switch]$Live,
    [switch]$SendEmail
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$envFile = Join-Path $projectRoot ".env"
$config = @{}
try {
    $triggerTime = [DateTime]::ParseExact($Time, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
} catch {
    throw "Time must use 24-hour HH:mm format, for example 08:17."
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Virtual environment not found. Create .venv before registering the task."
}
if ($SendEmail -and -not $Live) {
    throw "The -SendEmail option requires -Live."
}
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $parts = $trimmed -split "=", 2
        if ($parts.Count -eq 2) {
            $value = $parts[1].Trim()
            if ($value.Length -ge 2 -and
                (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                 ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $config[$parts[0].Trim()] = $value
        }
    }
}
function Get-ConfiguredValue([string]$Name) {
    return [string]$config[$Name]
}

if ($Live -and [string]::IsNullOrWhiteSpace((Get-ConfiguredValue "GEMINI_API_KEY"))) {
    throw "Live scheduling requires GEMINI_API_KEY in the project .env file."
}
if ($SendEmail) {
    if ((Get-ConfiguredValue "ENABLE_EMAIL").ToLowerInvariant() -notin @("true", "1", "yes", "on")) {
        throw "Email scheduling requires ENABLE_EMAIL=true."
    }
    foreach ($name in @("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "REPORT_TO")) {
        if ([string]::IsNullOrWhiteSpace((Get-ConfiguredValue $name))) {
            throw "Email scheduling requires $name to be configured."
        }
    }
}

$pythonArgs = @("-m", "wardprice", "run")
if ($Live) {
    $pythonArgs += "--live"
}
if ($SendEmail) {
    $pythonArgs += "--send-email"
}
$action = New-ScheduledTaskAction -Execute $pythonExe -Argument ($pythonArgs -join " ") -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $triggerTime
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask -and -not ([string]$existingTask.Description).StartsWith("WardPriceDaily daily task (")) {
    throw "A different scheduled task already uses this name. Choose another -TaskName."
}
$mode = if ($Live) { "LIVE Gemini" } else { "DRY RUN" }
if ($SendEmail) {
    $mode += " + Gmail"
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Description "WardPriceDaily daily task ($mode)" -Force | Out-Null
Write-Host "Registered '$TaskName' at $Time local time ($mode)."
Write-Host "Task runs when this Windows user is logged on. Change or remove it in Task Scheduler."