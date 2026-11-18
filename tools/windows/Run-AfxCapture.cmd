@echo off
cd /d "%~dp0"
echo Starting AFX capture...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-AfxCapture.ps1" %*
set "AFX_CAPTURE_EXIT=%ERRORLEVEL%"
pause
exit /b %AFX_CAPTURE_EXIT%
