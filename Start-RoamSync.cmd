@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-roamsync.ps1"
if errorlevel 1 (
  echo RoamSync could not start. See the error above.
  pause
  exit /b 1
)
echo RoamSync is ready at http://127.0.0.1:3000
pause
