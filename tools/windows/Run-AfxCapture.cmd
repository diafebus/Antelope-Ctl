@echo off
cd /d "%~dp0"
echo Starting AFX capture...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-AfxCapture.ps1"
pause
