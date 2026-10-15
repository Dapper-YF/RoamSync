[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$services = @(docker compose ps --status running --services)
$requiredServices = @("postgres", "api", "agent-worker", "web")
$missingServices = @($requiredServices | Where-Object { $services -notcontains $_ })
if ($missingServices.Count -gt 0) {
    foreach ($service in $missingServices) { Write-Output "FAIL ${service}: Docker service is not running" }
    Write-Output "DEMO NOT READY"
    exit 1
}
try {
    $apiResponse = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health/ready" -TimeoutSec 8 -UseBasicParsing
    if ($apiResponse.StatusCode -ne 200) { throw "HTTP $($apiResponse.StatusCode)" }
    Write-Output "PASS backend"
} catch {
    Write-Output "FAIL backend: HTTP health check failed"
    Write-Output "DEMO NOT READY"
    exit 1
}
try {
    $webResponse = Invoke-WebRequest -Uri "http://127.0.0.1:3000/" -TimeoutSec 8 -UseBasicParsing
    if ($webResponse.StatusCode -ne 200) { throw "HTTP $($webResponse.StatusCode)" }
    Write-Output "PASS frontend"
} catch {
    Write-Output "FAIL frontend: HTTP health check failed"
    Write-Output "DEMO NOT READY"
    exit 1
}

docker compose exec -T api uv run --no-sync python -m app.demo_preflight --worker-running
exit $LASTEXITCODE
