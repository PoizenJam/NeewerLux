@echo off
REM NeewerLux - HTTP Server Only (no GUI)

title NeewerLux HTTP Server
cd /d "%~dp0"

echo ====================================================
echo   NeewerLux - HTTP Server Mode
echo   Web dashboard: http://localhost:8080/
echo   API endpoint:  http://localhost:8080/NeewerLux/doAction?
echo   Press Ctrl+C to stop
echo ====================================================
echo.

python NeewerLux.py --http %*
