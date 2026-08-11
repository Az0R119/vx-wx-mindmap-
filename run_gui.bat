@echo off
REM ============================================================
REM  WeChat Message Summary - launcher (double-click)
REM  Uses project .venv first (has Pillow for optional compress),
REM  falls back to system python.
REM ============================================================
cd /d "%~dp0"
set "PYTHONPATH="
set "PYTHONHOME="

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0run_gui.py"
    exit /b 0
)
where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install: https://www.python.org/downloads/
    pause
    exit /b 1
)
python run_gui.py
pause
