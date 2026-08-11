@echo off
REM ============================================================
REM  WeChat Message Summary - build a single-file exe
REM  Double-click to build. Result: dist\wechat-summary.exe
REM  Requires Python; this venv already has PyInstaller.
REM ============================================================
cd /d "%~dp0"
set "PYTHONPATH="

if exist ".venv\Scripts\pythonw.exe" (
    set "PY=".venv\Scripts\python.exe
) else (
    where python >nul 2>nul || (echo Python not found & pause & exit /b 1)
    set "PY=python"
)

echo [1/2] Clean old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist wechat-summary.spec del /q wechat-summary.spec

echo [2/2] Building wechat-summary.exe (may take a minute)...
%PY% -m PyInstaller --noconfirm --onefile --windowed --name wechat-summary run_gui.py

echo.
echo Done! dist\wechat-summary.exe
pause
