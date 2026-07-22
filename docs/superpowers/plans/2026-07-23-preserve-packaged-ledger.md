# Preserve Packaged Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Preserve the customer's single strategy_ledger.json file through every Windows package rebuild.

**Architecture:** The batch file copies the package-side ledger to a uniquely named temporary backup before PyInstaller replaces the distribution folder. It restores the same file only after a successful build and configuration copy.

**Tech Stack:** Windows batch, PyInstaller, PowerShell verification.

## Global Constraints

- Preserve only dist/50qqScanner/strategy_ledger.json.
- Do not create an empty ledger if it did not exist before the build.
- Do not alter or delete strategy_ledger_data legacy files.
- A failed PyInstaller build must leave the temporary backup available and must not claim successful restoration.

---

### Task 1: Protected Windows Build Script

**Files:**
- Modify: D:/mycode/50qq/build_windows_exe.bat

**Interfaces:**
- Consumes: an optional existing dist/50qqScanner/strategy_ledger.json file.
- Produces: a rebuilt dist/50qqScanner directory containing the unchanged ledger file when it existed before the build.

- [ ] **Step 1: Create a known ledger and capture its SHA-256**

Run:

```powershell
$ledger = 'dist\50qqScanner\strategy_ledger.json'
$before = Get-FileHash -LiteralPath $ledger -Algorithm SHA256
$before.Hash
```

Expected: one SHA-256 value for the existing ledger.

- [ ] **Step 2: Update the batch build flow**

Insert this before the PyInstaller call:

```bat
set "LEDGER_FILE=dist\50qqScanner\strategy_ledger.json"
set "LEDGER_BACKUP=%TEMP%\50qqScanner_strategy_ledger_%RANDOM%%RANDOM%.json"
set "HAS_LEDGER_BACKUP=0"

if exist "%LEDGER_FILE%" (
    copy /Y "%LEDGER_FILE%" "%LEDGER_BACKUP%" >nul
    if errorlevel 1 (
        echo Failed to back up strategy ledger.
        exit /b 1
    )
    set "HAS_LEDGER_BACKUP=1"
)
```

After the configuration copy and before the success message, restore only when
HAS_LEDGER_BACKUP is 1, then delete the temporary backup.

- [ ] **Step 3: Run the batch build**

Run: cmd /c build_windows_exe.bat

Expected: build succeeds and reports the package executable. The interactive
pause can be bypassed by piping a newline or invoking the contained commands
from PowerShell during automated verification.

- [ ] **Step 4: Verify byte-for-byte ledger preservation**

Run:

```powershell
$after = Get-FileHash -LiteralPath 'dist\50qqScanner\strategy_ledger.json' -Algorithm SHA256
if ($after.Hash -ne $before.Hash) { throw 'Ledger content changed during package build.' }
Get-Item dist\50qqScanner\50qqScanner.exe, dist\50qqScanner\contracts_config.json
```

Expected: identical before/after SHA-256 values and both package files exist.

- [ ] **Step 5: Commit**

```powershell
git add build_windows_exe.bat
git commit -m "Preserve packaged strategy ledger during builds"
```

