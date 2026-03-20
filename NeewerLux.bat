@echo off
REM NeewerLux — Windows Launcher (no console window)
REM Uses pythonw.exe so no command prompt window appears.
REM For debugging with console output, run: python NeewerLux.py

cd /d "%~dp0"

REM Try pythonw first (no console), fall back to python
where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" pythonw "%~dp0NeewerLux.py" %*
) else (
    start "" python "%~dp0NeewerLux.py" %*
)
