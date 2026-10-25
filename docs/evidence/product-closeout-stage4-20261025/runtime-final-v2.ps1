param([string]$Mode='check')
$env:RS_PUBLIC_SOURCE='E:/Study/RoamSync-product-closeout-stage2-20261024'
$env:RS_PUBLIC_DSN='postgresql://agent_b_test:agent_b_test_only@127.0.0.1:15435/roamsync_a2_public_stage4_final_v2_20261025_test'
$env:RS_PUBLIC_API_PORT='18098'
$env:RS_PUBLIC_WEB_PORT='3098'
$env:RS_PUBLIC_OUTPUT='E:/Study/RoamSync-stage4-evidence-20261025/runtime-final-v2'
$env:RS_PUBLIC_TOKEN='closeout-stage4-synthetic-local-only'
$env:RS_PUBLIC_OWNER='closeout-stage4-synthetic-user'
$env:RS_PUBLIC_PROVIDER_ENV='E:/Study/RoamSync/.env'
$env:PYTHONUTF8='1'
if($Mode -eq 'web') {
 Set-Location E:/Study/RoamSync-product-closeout-stage2-20261024/web
 node node_modules/vite/bin/vite.js --config E:/Study/RoamSync-product-c2-evidence-20261022/public-runtime/vite.config.mjs --configLoader native
} else {
 & E:/Study/RoamSync/backend/.venv/Scripts/python.exe E:/Study/RoamSync-stage4-evidence-20261025/runtime_source_bound.py $Mode
}
