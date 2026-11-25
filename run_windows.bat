@echo off
setlocal
cd /d "%~dp0"

py -3.11 -c "import PyQt6; from xtquant import xtdata" >nul 2>nul
if errorlevel 1 (
    echo Python 3.11 with PyQt6 and QMT xtquant is required to run the source version.
    echo Please use the packaged 50qqScanner.exe or install the compatible dependencies in Python 3.11.
    pause
    exit /b 1
)

py -3.11 option_arbitrage_scanner.py

if errorlevel 1 (
    echo.
    echo Program exited with error.
    pause
)
