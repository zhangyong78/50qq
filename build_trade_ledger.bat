@echo off
setlocal
cd /d "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo Installing build dependencies...
    python -m pip install -r requirements.txt
)

echo Building TradeLedger...
pyinstaller --noconfirm --clean TradeLedger.spec

if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build completed: dist\TradeLedger\TradeLedger.exe
pause
