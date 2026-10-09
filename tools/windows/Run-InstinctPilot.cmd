@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-InstinctPilot.ps1"
if errorlevel 1 echo Pilot stopped. Review the evidence before touching any settings.
pause
