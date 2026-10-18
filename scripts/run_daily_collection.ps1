param(
    [int]$MaxRequests = 500
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LogDirectory = Join-Path $ProjectRoot 'outputs\collector'
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$LogPath = Join-Path $LogDirectory ("collection_{0}.log" -f (Get-Date -Format 'yyyyMMdd'))

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project virtual environment not found: $Python"
}
if ($MaxRequests -lt 1 -or $MaxRequests -gt 500) {
    throw 'MaxRequests must be between 1 and 500.'
}

"[$(Get-Date -Format o)] Starting scheduled collection." | Add-Content -LiteralPath $LogPath -Encoding utf8
& $Python -m wardprice collect-daily --all --live --max-requests $MaxRequests 2>&1 |
    Tee-Object -FilePath $LogPath -Append
$ExitCode = $LASTEXITCODE
if ($ExitCode -eq 0) {
    & $Python -m wardprice export 2>&1 | Tee-Object -FilePath $LogPath -Append
    if ($LASTEXITCODE -ne 0) {
        $ExitCode = $LASTEXITCODE
    }
}
"[$(Get-Date -Format o)] Finished with exit code $ExitCode." | Add-Content -LiteralPath $LogPath -Encoding utf8
exit $ExitCode
