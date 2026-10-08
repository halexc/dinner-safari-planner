@echo off
setlocal
cd /d "%~dp0"
echo Installing Cykelfest. Please keep this window open.
py -3.13 -c "import sys; sys.exit(sys.version_info[:2] != (3, 13))" >nul 2>&1
if not errorlevel 1 (
    py -3.13 scripts\install.py
    goto finished
)
python -c "import sys; sys.exit(sys.version_info[:2] != (3, 13))" >nul 2>&1
if not errorlevel 1 (
    python scripts\install.py
    goto finished
)
echo Python 3.13 was not found. Install the 64-bit version first.
echo See "INSTALL (For Dummies).md" for download links and instructions.
pause
exit /b 1
:finished
if errorlevel 1 (
    echo Installation failed. Read the error above for the next step.
    pause
    exit /b 1
)
pause
