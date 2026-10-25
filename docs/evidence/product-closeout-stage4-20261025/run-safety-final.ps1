$env:PYTHONUTF8='1'
& E:/Study/RoamSync/backend/.venv/Scripts/python.exe E:/Study/RoamSync-stage4-evidence-20261025/verify_real_objects_stage4.py *> E:/Study/RoamSync-stage4-evidence-20261025/real-object-safety-final.log
@{exit_code=$LASTEXITCODE;finished=(Get-Date -Format o)}|ConvertTo-Json|Set-Content E:/Study/RoamSync-stage4-evidence-20261025/real-object-safety-final-result.json
