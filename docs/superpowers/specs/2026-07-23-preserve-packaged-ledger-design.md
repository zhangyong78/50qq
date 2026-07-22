# Preserve Packaged Ledger Design

## Goal

Keep the customer ledger at
dist/50qqScanner/strategy_ledger.json intact when rebuilding the Windows
scanner package.

## Build Flow

1. Before PyInstaller runs, check whether the packaged ledger exists.
2. If it exists, copy it to a uniquely named file under %TEMP%.
3. Run the existing PyInstaller build unchanged.
4. Copy contracts_config.json to the recreated package directory.
5. If a temporary ledger backup exists, copy it back as
   dist/50qqScanner/strategy_ledger.json, then remove the temporary backup.

No ledger file is created when none existed before the build. The legacy
strategy_ledger_data directory is not moved, changed or deleted.

## Verification

Create a known strategy_ledger.json, run the build script logic, and verify
the restored package file has identical content. Also verify the normal
package executable and configuration file exist.

