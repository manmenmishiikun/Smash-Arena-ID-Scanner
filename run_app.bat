@echo off
cd /d "%~dp0"
venv\Scripts\python.exe main.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: See the message above.
    pause
)
