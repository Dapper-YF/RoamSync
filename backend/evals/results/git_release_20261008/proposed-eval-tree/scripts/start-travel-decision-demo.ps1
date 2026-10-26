[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
# The repository .env is the configured production-demo source. An unrelated
# inherited PowerShell value must not silently override it for Compose.
if (Test-Path Env:TAVILY_API_KEY) {
    Remove-Item Env:TAVILY_API_KEY
    Write-Output "Ignoring inherited TAVILY_API_KEY for this process; Docker Compose will read .env."
}
docker compose up -d --build api agent-worker web
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

for ($attempt = 0; $attempt -lt 12; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health/ready" -TimeoutSec 5 -UseBasicParsing
        if ($response.StatusCode -eq 200) { break }
    } catch { Start-Sleep -Seconds 3 }
}

& "$PSScriptRoot\demo-preflight.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "Services ready. Existing trip data preserved; no reset is performed."
