$env:PYTHONUTF8='1'
& E:/Study/RoamSync/backend/.venv/Scripts/python.exe E:/Study/RoamSync-stage3-evidence-20261024/run_batch.py --output E:/Study/RoamSync-stage4-evidence-20261025/full-final-v2 --tests 'tests --ignore=tests/test_draft_promotion.py --ignore=tests/test_place_content_postgres.py' *> E:/Study/RoamSync-stage4-evidence-20261025/full-final-v2-command.log
@{exit_code=$LASTEXITCODE;finished=(Get-Date -Format o)} | ConvertTo-Json | Set-Content E:/Study/RoamSync-stage4-evidence-20261025/full-final-v2-result.json
