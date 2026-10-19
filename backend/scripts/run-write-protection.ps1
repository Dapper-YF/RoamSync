param([string[]]$TestArgs = @('tests/test_formal_write_protection.py', '-q', '--tb=short'), [string]$Evidence = 'focused', [switch]$Full)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$name = 'roamsync-write-protection-pg'
if ((docker inspect --format '{{index .Config.Labels "roamsync.task"}}' $name) -ne 'write-protection-20261019') { throw 'Dedicated test container required' }
$binding = docker port $name 5432
if ($binding -notmatch '^127\.0\.0\.1:(\d+)$') { throw 'Only loopback test PG allowed' }
$testPort = $Matches[1]
$env:APP_ENV = 'test'
$env:DATABASE_URL = "postgresql+psycopg://write_test:write_test_only@127.0.0.1:$testPort/roamsync_test_write_protection"
$env:LANGGRAPH_DATABASE_URL = "postgresql://write_test:write_test_only@127.0.0.1:$testPort/roamsync_test_write_protection"
$env:PLANNER_API_KEY = ''; $env:PLANNER_MODEL = ''; $env:AMAP_REST_KEY = ''; $env:TAVILY_API_KEY = ''; $env:ROAMSYNC_TAVILY_API_KEY = ''
$env:ALLOW_MAP_ESTIMATES = 'true'
if ($Full) {
    $found = docker exec $name psql -U write_test -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='promotion_test'"
    if ($found -ne '1') {
        docker exec $name psql -U write_test -d postgres -c 'CREATE DATABASE promotion_test OWNER write_test'
        if ($LASTEXITCODE -ne 0) { throw 'Dedicated promotion test DB creation failed' }
    }
    $env:PROMOTION_TEST_DATABASE_URL = "postgresql+psycopg://write_test:write_test_only@127.0.0.1:$testPort/promotion_test"
    $TestArgs = @('tests', '-q', '--tb=short')
}
$python = 'E:/Study/RoamSync/backend/.venv/Scripts/python.exe'
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Isolated migrations failed' }
$out = '../docs/evidence/write-protection'
New-Item -ItemType Directory -Force -Path $out | Out-Null
& $python scripts/run_write_protection_tests.py @TestArgs "--junitxml=$out/$Evidence.xml" 2>&1 | Tee-Object -FilePath "$out/$Evidence.log"
exit $LASTEXITCODE
