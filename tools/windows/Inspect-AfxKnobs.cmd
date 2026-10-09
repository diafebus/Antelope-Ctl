@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Inspect-AfxPanel.ps1" -InspectKnobHover
if errorlevel 1 echo Knob inspection stopped. Leave this message visible for troubleshooting.
pause
