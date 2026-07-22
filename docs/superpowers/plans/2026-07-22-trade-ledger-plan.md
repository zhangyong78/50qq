# Trade Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Windows desktop ledger for recording ETF spot and option trades and calculating each day's cash-flow net profit.

**Architecture:** `trade_ledger.py` contains pure record, summary, and JSON-store functions plus the PyQt6 window. The window selects one date at a time, saves that date's records immediately, and renders summary cards above the editable record table. A separate PyInstaller spec creates `TradeLedger.exe` without QMT dependencies.

**Tech Stack:** Python 3.10, PyQt6, standard-library JSON, `unittest`, PyInstaller.

## Global Constraints

- Store each day beside the executable under `ledger_data/YYYY-MM-DD.json`.
- Spot gross amount is `price * quantity`; option gross amount is `price * quantity * 10000`.
- Daily net profit is sell gross amount minus buy gross amount minus fee.
- No position cost, unrealized P&L, automatic fee calculation, QMT import, cloud sync, or monthly reports.
- Build output is `dist/TradeLedger/TradeLedger.exe`.

---

### Task 1: Implement testable trade math and local storage

**Files:**
- Create: `tests/test_trade_ledger.py`
- Create: `trade_ledger.py`

**Interfaces:**
- `trade_multiplier(instrument_type: str) -> int` returns `1` for `现货` and `10000` for `期权`.
- `trade_gross_amount(record: dict[str, Any]) -> float`.
- `calculate_day_summary(records: list[dict[str, Any]]) -> dict[str, float]` returns `buy_amount`, `sell_amount`, `fee_amount`, and `net_profit`.
- `LedgerStore(data_dir: Path)` loads and saves list-of-dict records by `date`.

- [ ] **Step 1: Write failing unit tests**

```python
def test_trade_amount_uses_spot_and_option_multipliers(self):
    self.assertEqual(trade_gross_amount({"instrument_type": "现货", "price": 3.02, "quantity": 10000}), 30200.0)
    self.assertEqual(trade_gross_amount({"instrument_type": "期权", "price": 0.0215, "quantity": 2}), 430.0)

def test_daily_summary_uses_cash_flow_minus_fees(self):
    records = [
        {"instrument_type": "现货", "direction": "买入", "price": 3.02, "quantity": 10000, "fee": 6.04},
        {"instrument_type": "期权", "direction": "卖出", "price": 0.0215, "quantity": 2, "fee": 0.0},
    ]
    self.assertEqual(calculate_day_summary(records), {
        "buy_amount": 30200.0, "sell_amount": 430.0, "fee_amount": 6.04, "net_profit": -29776.04,
    })
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_trade_ledger -v`

Expected: import failure because `trade_ledger.py` does not exist.

- [ ] **Step 3: Add minimal record and storage implementation**

```python
def trade_multiplier(instrument_type: str) -> int:
    return 10000 if instrument_type == "期权" else 1

def trade_gross_amount(record: dict[str, Any]) -> float:
    return float(record.get("price", 0.0)) * float(record.get("quantity", 0.0)) * trade_multiplier(str(record.get("instrument_type", "现货")))

def calculate_day_summary(records: list[dict[str, Any]]) -> dict[str, float]:
    buy_amount = sum(trade_gross_amount(record) for record in records if record.get("direction") == "买入")
    sell_amount = sum(trade_gross_amount(record) for record in records if record.get("direction") == "卖出")
    fee_amount = sum(float(record.get("fee", 0.0)) for record in records)
    return {"buy_amount": buy_amount, "sell_amount": sell_amount, "fee_amount": fee_amount, "net_profit": sell_amount - buy_amount - fee_amount}
```

- [ ] **Step 4: Add JSON round-trip test and implementation**

```python
with TemporaryDirectory() as temp_dir:
    store = LedgerStore(Path(temp_dir))
    store.save("2026-07-22", [{"code": "510050.SH", "direction": "买入"}])
    self.assertEqual(store.load("2026-07-22"), [{"code": "510050.SH", "direction": "买入"}])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest tests.test_trade_ledger -v`

Expected: all trade math and storage tests pass.

### Task 2: Build the PyQt6 ledger window

**Files:**
- Modify: `trade_ledger.py`
- Test: `tests/test_trade_ledger.py`

**Interfaces:**
- `LedgerWindow` owns the selected date, `LedgerStore`, current records, form controls, summary labels, and table actions.
- `main() -> int` creates `QApplication`, shows `LedgerWindow`, and executes the event loop.

- [ ] **Step 1: Create the window layout**

```python
class LedgerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ETF期权交易小账本")
        self.setMinimumSize(1120, 680)
        self.store = LedgerStore(application_data_dir())
        self.records: list[dict[str, Any]] = []
        self._build_ui()
        self.load_selected_date()
```

- [ ] **Step 2: Add entry and edit actions**

```python
def save_form_record(self) -> None:
    record = self._record_from_form()
    if record is None:
        return
    if self.editing_index is None:
        self.records.append(record)
    else:
        self.records[self.editing_index] = record
    self._persist_and_refresh()

def delete_selected_record(self) -> None:
    if self.editing_index is None:
        return
    del self.records[self.editing_index]
    self._persist_and_refresh()
```

- [ ] **Step 3: Verify window construction and source compilation**

Run: `python -m py_compile trade_ledger.py`

Expected: exit code 0.

### Task 3: Add standalone packaging and complete verification

**Files:**
- Create: `TradeLedger.spec`
- Create: `build_trade_ledger.bat`

**Interfaces:**
- `TradeLedger.spec` builds windowed executable `TradeLedger` from `trade_ledger.py`.
- `build_trade_ledger.bat` invokes `pyinstaller --noconfirm --clean TradeLedger.spec`.

- [ ] **Step 1: Create the PyInstaller spec**

```python
a = Analysis(['trade_ledger.py'], pathex=[], binaries=[], datas=[], hiddenimports=[])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TradeLedger', console=False)
coll = COLLECT(exe, a.binaries, a.datas, name='TradeLedger')
```

- [ ] **Step 2: Create the build script**

```bat
@echo off
cd /d "%~dp0"
pyinstaller --noconfirm --clean TradeLedger.spec
```

- [ ] **Step 3: Run all tests, compile, and build**

Run: `python -m unittest discover -v; python -m py_compile trade_ledger.py; pyinstaller --noconfirm --clean TradeLedger.spec`

Expected: all tests pass and `dist/TradeLedger/TradeLedger.exe` exists.

- [ ] **Step 4: Commit**

```bash
git add trade_ledger.py TradeLedger.spec build_trade_ledger.bat tests/test_trade_ledger.py docs/superpowers/plans/2026-07-22-trade-ledger-plan.md && git commit -m "Add standalone trade ledger"
```
