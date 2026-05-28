@echo off
setlocal
cd /d "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo Installing build dependencies...
    python -m pip install -r requirements.txt
)

echo Building Windows GUI executable...
pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name 50qqScanner ^
  --add-data "contracts_config.json;." ^
  option_arbitrage_scanner.py

if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build completed: dist\50qqScanner\50qqScanner.exe
pause
