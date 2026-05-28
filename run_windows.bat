@echo off
setlocal
cd /d "%~dp0"

python option_arbitrage_scanner.py

if errorlevel 1 (
    echo.
    echo Program exited with error.
    pause
)
