@echo off
cd /d "%~dp0"
echo Starting automatic knob inspection...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Inspect-AfxKnobs.ps1"
if errorlevel 1 echo Knob inspection stopped. Leave this message visible for troubleshooting.
pause
