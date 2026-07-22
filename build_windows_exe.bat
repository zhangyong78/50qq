@echo off
setlocal
cd /d "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo Installing build dependencies...
    python -m pip install -r requirements.txt
)

set "LEDGER_FILE=dist\50qqScanner\strategy_ledger.json"
set "LEDGER_BACKUP=%TEMP%\50qqScanner_strategy_ledger_%RANDOM%%RANDOM%.json"
set "HAS_LEDGER_BACKUP=0"

if exist "%LEDGER_FILE%" (
    echo Backing up existing strategy ledger...
    copy /Y "%LEDGER_FILE%" "%LEDGER_BACKUP%" >nul
    if errorlevel 1 (
        echo Failed to back up strategy ledger.
        pause
        exit /b 1
    )
    set "HAS_LEDGER_BACKUP=1"
)

echo Building Windows GUI executable...
pyinstaller ^
  --noconfirm ^
  --clean ^
  50qqScanner.spec

if errorlevel 1 (
    echo.
    echo Build failed.
    if "%HAS_LEDGER_BACKUP%"=="1" (
        if not exist "dist\50qqScanner" mkdir "dist\50qqScanner"
        copy /Y "%LEDGER_BACKUP%" "%LEDGER_FILE%" >nul
        echo Existing strategy ledger restored.
    )
    pause
    exit /b 1
)

copy /Y "contracts_config.json" "dist\50qqScanner\contracts_config.json" >nul

if "%HAS_LEDGER_BACKUP%"=="1" (
    copy /Y "%LEDGER_BACKUP%" "%LEDGER_FILE%" >nul
    del /Q "%LEDGER_BACKUP%" >nul 2>nul
    echo Existing strategy ledger restored.
)

echo.
echo Build completed: dist\50qqScanner\50qqScanner.exe
pause
