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
  50qqScanner.spec

if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

copy /Y "contracts_config.json" "dist\50qqScanner\contracts_config.json" >nul

echo.
echo Build completed: dist\50qqScanner\50qqScanner.exe
pause
