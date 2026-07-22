# Selected Scan Row To Post-Market Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Prefill the manual post-market ledger from a selected scanner opportunity row without automatically saving a transaction.

**Architecture:** The scanner converts a selected rendered row into a plain prefill dictionary using the same bid/ask side as the relevant strategy formula. The ledger dialog accepts that dictionary and updates only its editable form widgets.

**Tech Stack:** Python 3.10, PyQt6, unittest, PyInstaller.

## Global Constraints

- No selected scanner row must retain the current blank manual-ledger behavior.
- Selection prefill defaults to one contract and 10,000 spot shares.
- Prefilled quote values are editable and are not automatically persisted.
- Modes 2 and 3 remain passive settlement with zero option fees.
- Preserve the existing double-click screen-freeze behavior and all current scan calculations.
- Preserve unrelated uncommitted scanner exercise-status changes and ledger JSON data.
- Keep all ledger records in one `strategy_ledger.json` file beside the
  scanner configuration; selected-month totals are calculated by filtering.

---

### Task 1: Editable Ledger Prefill

**Files:**
- Modify: D:/mycode/50qq/post_market_ledger.py
- Modify: D:/mycode/50qq/tests/test_post_market_ledger.py

**Interfaces:**
- Produces: StrategyLedgerDialog.apply_prefill(prefill: dict[str, Any]) -> None.
- Consumes prefill keys: mode, etf_code, option_code, strike, stock_price, option_premium, stock_shares and option_contracts.

- [ ] **Step 1: Write the failing dialog test**

```python
def test_prefill_updates_form_without_creating_a_record(self):
    dialog = StrategyLedgerDialog(Path(temp_dir))
    dialog.apply_prefill({
        "mode": "mode2", "etf_code": "510050", "option_code": "10011695.SH",
        "strike": 3.10, "stock_price": 3.0900, "option_premium": 201.0,
        "stock_shares": 10000, "option_contracts": 1,
    })
    self.assertEqual(dialog.mode_combo.currentData(), "mode2")
    self.assertEqual(dialog.stock_price_spin.value(), 3.09)
    self.assertEqual(dialog.option_premium_spin.value(), 201.0)
    self.assertEqual(dialog.table.rowCount(), 0)
    self.assertEqual(dialog.save_button.text(), "新增记录")
```

- [ ] **Step 2: Run the focused test to verify failure**

Run: python -m unittest tests.test_post_market_ledger -v

Expected: FAIL because apply_prefill does not exist.

- [ ] **Step 3: Implement only widget population**

```python
def apply_prefill(self, prefill: dict[str, Any]) -> None:
    self.clear_form()
    mode_index = self.mode_combo.findData(str(prefill.get("mode", "mode1")))
    self.mode_combo.setCurrentIndex(max(mode_index, 0))
    self.etf_code_edit.setText(str(prefill.get("etf_code", "")))
    self.option_code_edit.setText(str(prefill.get("option_code", "")))
    self.strike_spin.setValue(float(prefill.get("strike", 0.0)))
    self.stock_price_spin.setValue(float(prefill.get("stock_price", 0.0)))
    self.option_premium_spin.setValue(float(prefill.get("option_premium", 0.0)))
    self.stock_shares_spin.setValue(int(prefill.get("stock_shares", 10000)))
    self.option_contracts_spin.setValue(int(prefill.get("option_contracts", 1)))
```

Do not call calculate_settled_profit, save or add a table record here.

- [ ] **Step 4: Run ledger tests**

Run: python -m unittest tests.test_post_market_ledger -v

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add post_market_ledger.py tests/test_post_market_ledger.py
git commit -m "Add editable ledger prefill"
```

### Task 2: Selected Scanner Row Mapping And Entry Point

**Files:**
- Modify: D:/mycode/50qq/option_arbitrage_scanner.py:2930-3140
- Modify: D:/mycode/50qq/option_arbitrage_scanner.py:3681-3686
- Modify: D:/mycode/50qq/tests/test_scanner_post_market_entry.py

**Interfaces:**
- Produces: MainWindow._selected_ledger_prefill() -> dict[str, Any] | None.
- Consumes: StrategyLedgerDialog.apply_prefill(prefill: dict[str, Any]) -> None.

- [ ] **Step 1: Write a failing selected-row mapping test**

```python
def test_selected_mode2_row_maps_bid_prices_to_ledger(self):
    window.rendered_rows_by_mode["模式2"] = [{
        "pool": "50ETF", "option_code": "10011695.SH", "strike": 3.10,
        "spot_bid": 3.09, "spot_ask": 3.10, "option_bid": 0.0201, "option_ask": 0.0205,
    }]
    window.mode_tables["模式2"].setRowCount(1)
    window.mode_tables["模式2"].selectRow(0)
    self.assertEqual(window._selected_ledger_prefill(), {
        "mode": "mode2", "etf_code": "50ETF", "option_code": "10011695.SH",
        "strike": 3.10, "stock_price": 3.09, "option_premium": 201.0,
        "stock_shares": 10000, "option_contracts": 1,
    })
```

Add a second test proving open_post_market_ledger calls apply_prefill when a selected-row dictionary is available and still opens the dialog.

- [ ] **Step 2: Run the scanner entry tests to verify failure**

Run: python -m unittest tests.test_scanner_post_market_entry -v

Expected: FAIL because _selected_ledger_prefill does not exist.

- [ ] **Step 3: Implement selection lookup and strategy-price mapping**

Add _selected_ledger_prefill that iterates mode_tables, reads the first selected row index, retrieves the matching item from rendered_rows_by_mode and maps:
- 模式1 to mode1, spot_ask and option_ask times 10,000.
- 模式2 to mode2, spot_bid and option_bid times 10,000.
- 模式3 to mode3, spot_ask and option_bid times 10,000.
- 模式4 to mode4, spot_bid and option_ask times 10,000.

Return None when there is no valid selection. Update open_post_market_ledger to create the dialog, call apply_prefill only for a non-None prefill, then execute the dialog. Do not change the existing double-click binding.

- [ ] **Step 4: Run full verification**

Run: python -m unittest discover -v

Expected: PASS.

Run: python -m py_compile option_arbitrage_scanner.py post_market_ledger.py

Expected: exit code 0.

- [ ] **Step 5: Rebuild package**

```powershell
pyinstaller --noconfirm --clean 50qqScanner.spec
Copy-Item -LiteralPath contracts_config.json -Destination dist\50qqScanner\contracts_config.json -Force
Get-Item dist\50qqScanner\50qqScanner.exe, dist\50qqScanner\contracts_config.json
```

Expected: both files exist in D:/mycode/50qq/dist/50qqScanner.

- [ ] **Step 6: Stage only the new feature scope**

Review git diff before staging. Do not stage unrelated exercise-status changes in option_arbitrage_scanner.py or existing strategy_ledger_data files.
