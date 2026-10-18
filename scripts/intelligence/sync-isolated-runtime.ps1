param(
    [Parameter(Mandatory=$true)][string]$ExistingCompose,
    [Parameter(Mandatory=$true)][string]$ExistingEnv
)
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$project = 'roamsync-product-20261016'
$containers = @("$project-api-1", "$project-worker-1")
foreach ($container in $containers) {
    $isolated = & docker exec $container python -c 'import os;print(os.environ.get("ROAMSYNC_ISOLATED_INTEGRATION")=="1" and os.environ.get("DATABASE_URL", "").endswith("/roamsync_v2_integration"))'
    if ($LASTEXITCODE -ne 0 -or $isolated.Trim() -ne 'True') { throw "Refuse nonisolated target $container" }
}
$folder = Join-Path $workspace 'artifacts/runtime-followup-20261018'
New-Item -ItemType Directory -Force $folder | Out-Null
$source = (Join-Path $workspace 'backend/app').Replace('\','/')
$override = Join-Path $folder 'source.override.yaml'
@"
services:
  api:
    volumes:
      - type: bind
        source: '$source'
        target: /app/app
        read_only: true
  worker:
    volumes:
      - type: bind
        source: '$source'
        target: /app/app
        read_only: true
"@ | Set-Content -LiteralPath $override -Encoding utf8
# Existing project/env preserve its database, credentials, loopback ports and commands.
# Match the existing product launcher: provider settings first, isolated DB/token last.
# No build, migration, product database initializer, production restart or DB copy.
$providerEnv = Join-Path $workspace '.env'
if (-not (Test-Path -LiteralPath $providerEnv)) { throw 'Missing existing provider configuration' }
$composeArgs = @('compose', '--env-file', $providerEnv, '--env-file', $ExistingEnv,
    '-p', $project, '-f', $ExistingCompose, '-f', $override, '--profile', 'worker')
# Inspect resolved configuration only in memory; it contains private credentials.
try { $candidate = (& docker @composeArgs config --format json) | ConvertFrom-Json }
catch { throw 'Unable to validate isolated runtime configuration' }
if ($LASTEXITCODE -ne 0) { throw 'Invalid isolated runtime configuration' }
foreach ($service in @($candidate.services.api, $candidate.services.worker)) {
    if ($service.environment.ROAMSYNC_ISOLATED_INTEGRATION -ne '1' -or
        $service.environment.DATABASE_URL -notmatch '@postgres:5432/roamsync_v2_integration$' -or
        (($service.command -join ' ') -match 'alembic|integration_init')) {
        throw 'Refuse changed database identity, migration or product initializer'
    }
}
$ports = @($candidate.services.api.ports)
if ($ports.Count -ne 1 -or $ports[0].host_ip -ne '127.0.0.1' -or $ports[0].published -ne '18004') {
    throw 'Refuse changed network exposure'
}
& docker @composeArgs up -d --no-deps --wait api worker
if ($LASTEXITCODE -ne 0) { throw 'Isolated source synchronization failed' }
foreach ($container in $containers) {
    $mount = & docker inspect $container --format '{{json .Mounts}}' | ConvertFrom-Json
    $app = $mount | Where-Object { $_.Destination -eq '/app/app' }
    if ($app.RW -or $app.Source.Replace('\','/') -ne $source) { throw "Source binding mismatch: $container" }
}
Write-Output 'Isolated API/worker now use canonical app source; production and database volumes unchanged.'
foreach ($container in $containers) {
    $configured = & docker exec $container python -c 'from app.config import get_settings;s=get_settings();print(bool(s.amap_rest_key) and bool(s.planner_api_key))'
    if ($LASTEXITCODE -ne 0 -or $configured.Trim() -ne 'True') { throw "Provider configuration not loaded: $container" }
}
