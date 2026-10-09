@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-AfxScan.ps1"
if errorlevel 1 echo Scan stopped. Its launch log is saved automatically in results.
pause
