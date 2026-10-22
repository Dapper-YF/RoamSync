[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ($sourceRoot.TrimEnd('\') -ine 'E:\Study\RoamSync') {
    throw 'Verification must run from E:\Study\RoamSync.'
}
$containers = @('roamsync-postgres', 'roamsync-api', 'roamsync-agent-worker-1',
    'roamsync-agent-checkpoint-init-1', 'roamsync-web')
foreach ($container in $containers) {
    $raw = & docker inspect $container
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect $container" }
    $info = @($raw | ConvertFrom-Json)[0]
    if ($info.Config.Labels.'com.docker.compose.project.working_dir' -ine $sourceRoot) {
        throw "$container was deployed from a different directory."
    }
    if ($container -like '*checkpoint-init*') {
        if ($info.State.ExitCode -ne 0) { throw 'Checkpoint initialization failed.' }
    } elseif (-not $info.State.Running) { throw "$container is not running." }
    Write-Output "PASS deployment source: $container"
}

$hashCode = @'
import hashlib, json
from pathlib import Path
root = Path('/app')
paths = [p for folder in ('app', 'migrations') for p in (root / folder).rglob('*')
         if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
paths += [root / name for name in ('alembic.ini', 'pyproject.toml', 'uv.lock')]
print(json.dumps({p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in paths}))
'@
$backendRoot = Join-Path $sourceRoot 'backend'
$expectedPaths = @()
foreach ($folder in @('app', 'migrations')) {
    $expectedPaths += @(Get-ChildItem -LiteralPath (Join-Path $backendRoot $folder) -Recurse -File |
        Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and $_.Extension -ne '.pyc' } |
        ForEach-Object { $_.FullName.Substring($backendRoot.Length + 1).Replace('\', '/') })
}
$expectedPaths += @('alembic.ini', 'pyproject.toml', 'uv.lock')
foreach ($container in @('roamsync-api', 'roamsync-agent-worker-1')) {
    $rawHashes = $hashCode | & docker exec -i $container python -
    if ($LASTEXITCODE -ne 0) { throw "Cannot hash $container source." }
    $hashes = $rawHashes | ConvertFrom-Json
    $actualPaths = @($hashes.PSObject.Properties.Name)
    if (@(Compare-Object $expectedPaths $actualPaths).Count -gt 0) {
        throw "$container source file list differs from official source."
    }
    foreach ($relative in $expectedPaths) {
        $localHash = (Get-FileHash -LiteralPath (Join-Path $backendRoot $relative) -Algorithm SHA256).Hash
        if ($localHash -ine $hashes.$relative) { throw "$container source mismatch: $relative" }
    }
    Write-Output "PASS official backend source: $container ($($expectedPaths.Count) files)"
    $modelCode = "from app.config import get_settings; s=get_settings(); assert s.planner_provider == 'glm' and s.planner_model == 'glm-5.3-flash' and s.planner_api_key.get_secret_value(), 'GLM configuration missing or incorrect'; print('PASS GLM configuration: glm-5.3-flash')"
    & docker exec $container python -c $modelCode
    if ($LASTEXITCODE -ne 0) { throw "$container model configuration is incorrect." }
}
foreach ($url in @('http://127.0.0.1:8000/health/ready', 'http://127.0.0.1:3000/healthz')) {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -ne 200) { throw "Health check failed: $url" }
    Write-Output "PASS health: $url"
}
$evidenceRoot = Join-Path $sourceRoot 'artifacts/release-verification'
New-Item -ItemType Directory -Path $evidenceRoot -Force | Out-Null
& python (Join-Path $PSScriptRoot 'verify-release.py') --output (Join-Path $evidenceRoot 'latest.json')
if ($LASTEXITCODE -ne 0) { throw 'Build manifest/source/artifact verification failed. Health alone cannot certify this release.' }
