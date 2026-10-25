$ErrorActionPreference='Continue'
Set-Location E:/Study/RoamSync-product-closeout-stage2-20261024/web
pnpm exec vitest run --maxWorkers=2 *> E:/Study/RoamSync-stage4-evidence-20261025/web-final-test.log
$testExit=$LASTEXITCODE
pnpm typecheck *> E:/Study/RoamSync-stage4-evidence-20261025/web-final-type.log
$typeExit=$LASTEXITCODE
pnpm build *> E:/Study/RoamSync-stage4-evidence-20261025/web-final-build.log
$buildExit=$LASTEXITCODE
@{tests=$testExit;typecheck=$typeExit;build=$buildExit;finished=(Get-Date -Format o)}|ConvertTo-Json|Set-Content E:/Study/RoamSync-stage4-evidence-20261025/web-final-result.json
