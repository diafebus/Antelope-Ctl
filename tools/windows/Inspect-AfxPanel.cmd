@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Inspect-AfxPanel.ps1"
if errorlevel 1 echo Inspection failed. Leave this message visible for troubleshooting.
pause
