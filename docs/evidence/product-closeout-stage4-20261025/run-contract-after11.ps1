$env:PYTHONUTF8='1'
& E:/Study/RoamSync/backend/.venv/Scripts/python.exe E:/Study/RoamSync-stage4-evidence-20261025/run_recorded_v4.py --app-root E:/Study/RoamSync-product-closeout-stage2-20261024 --settings-source E:/Study/RoamSync/.env --database-name roamsync_agent_b3_stage4_contract_after11_test --label stage4-contract-after11 --fixture E:/Study/RoamSync-stage4-evidence-20261025/contract-candidate-after11-fixture.json --output E:/Study/RoamSync-stage4-evidence-20261025/contract-real-after11.json *> E:/Study/RoamSync-stage4-evidence-20261025/contract-real-after11.log
@{exit_code=$LASTEXITCODE;finished=(Get-Date -Format o)}|ConvertTo-Json|Set-Content E:/Study/RoamSync-stage4-evidence-20261025/contract-real-after11-result.json


