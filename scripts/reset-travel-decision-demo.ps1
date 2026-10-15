[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$services = @(docker compose ps --status running --services)
if ($services -notcontains "api") {
    Write-Error "RoamSync API container is not running. Start Docker Compose first."
    exit 1
}

docker compose exec -T api uv run --no-sync python -m app.travel_decision_demo --reset
exit $LASTEXITCODE
