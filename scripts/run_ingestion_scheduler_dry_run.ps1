param(
    [string]$PilotDatabase = '.\state\ward_prices.ingestion_pilot.sqlite3',
    [string]$TargetsDatabase = '.\state\ward_prices.sqlite3'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project virtual environment not found: $Python"
}

# This only previews today's inbox, checks the isolated pilot DB, and writes a
# local daily report. It does not register a Windows task or access the network.
& $Python -m wardprice.ingestion_pilot scheduler-dry-run `
    --pilot-db $PilotDatabase `
    --targets-db $TargetsDatabase
exit $LASTEXITCODE
