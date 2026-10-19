#requires -Version 7.0
param([string]$Evidence='focused', [switch]$Full, [switch]$Favorites)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$container='roamsync-natural-assistant-pg'
$details=docker inspect $container | ConvertFrom-Json
if ($details[0].Config.Labels.'roamsync.task' -ne 'natural-assistant-20261019') { throw 'Dedicated integration container required' }
$binding=docker port $container 5432
if ($binding -notmatch '^127\.0\.0\.1:(\d+)$') { throw 'Loopback PostgreSQL required' }
$testPort=$Matches[1]
$env:APP_ENV='test'
$env:DATABASE_URL="postgresql+psycopg://write_test:write_test_only@127.0.0.1:$testPort/roamsync_test_write_protection"
$env:LANGGRAPH_DATABASE_URL="postgresql://write_test:write_test_only@127.0.0.1:$testPort/roamsync_test_write_protection"
$env:PLANNER_API_KEY=''; $env:PLANNER_MODEL=''; $env:AMAP_REST_KEY=''; $env:TAVILY_API_KEY=''; $env:ROAMSYNC_TAVILY_API_KEY=''
$env:ALLOW_MAP_ESTIMATES='true'
$python='E:/Study/RoamSync/backend/.venv/Scripts/python.exe'
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
$cases=@('tests/test_formal_write_protection.py','tests/test_formal_write_integration_review.py','-q','--tb=short')
if ($Full -or $Favorites) {
    $dbName=if ($Favorites) {'roamsync_test'} else {'promotion_test'}
    $found=docker exec $container psql -U write_test -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$dbName'"
    if ($found -ne '1') {
        docker exec $container psql -U write_test -d postgres -c "CREATE DATABASE $dbName OWNER write_test"
        if ($LASTEXITCODE -ne 0) { throw 'Test DB creation failed' }
    }
    $env:PROMOTION_TEST_DATABASE_URL="postgresql+psycopg://write_test:write_test_only@127.0.0.1:$testPort/promotion_test"
    $cases=@('tests','-q','--tb=short')
}
$out='../docs/evidence/natural-assistant'
New-Item -ItemType Directory -Force $out | Out-Null
if ($Favorites) {
    $env:DATABASE_URL="postgresql+psycopg://write_test:write_test_only@127.0.0.1:$testPort/roamsync_test"
    & $python -m pytest tests/test_place_content_postgres.py -q -rA "--junitxml=$out/$Evidence.xml" 2>&1 | Tee-Object "$out/$Evidence.log"
} else {
    & $python scripts/run_write_protection_tests.py @cases "--junitxml=$out/$Evidence.xml" 2>&1 | Tee-Object "$out/$Evidence.log"
}
exit $LASTEXITCODE
