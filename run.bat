@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please run install.bat first. See "INSTALL (For Dummies).md".
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m cykelfest_routing %*
if errorlevel 1 (
    echo Cykelfest could not start. Read the error above, or run install.bat again.
    pause
    exit /b 1
)
