# Integrated Post-Market Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual, monthly post-market ledger for actually exercised ETF option strategies to the existing 50qqScanner executable.

**Architecture:** Create `post_market_ledger.py` as a self-contained module containing the four settled-profit formulas, JSON month storage and the PyQt dialog. Keep `option_arbitrage_scanner.py` responsible only for opening that dialog with its resolved configuration directory. This preserves the existing quote worker and strategy scan paths.

**Tech Stack:** Python 3.10, PyQt6, JSON files, `unittest`, PyInstaller.

## Global Constraints

- All ledger inputs are manually entered and represent positions already settled by exercise or assignment.
- Validate `stock_shares == option_contracts * 10000`.
- Defaults are stock commission `0.0002`, option buy-open `2` yuan/contract and active exercise `4` yuan/contract.
- Modes 2 and 3 are passive settlement and charge neither option buy-open nor exercise fees.
- Save data beside `contracts_config.json` in `strategy_ledger_data/YYYY-MM.json`.
- Preserve the current uncommitted scanner exercise-status changes; do not discard or rewrite them.

---

### Task 1: Settlement Domain And Monthly Storage

**Files:**
- Create: `D:/mycode/50qq/post_market_ledger.py`
- Create: `D:/mycode/50qq/tests/test_post_market_ledger.py`

**Interfaces:**
- Produces: `calculate_settled_profit(record: dict[str, Any]) -> float`.
- Produces: `format_settlement_formula(record: dict[str, Any]) -> str`.
- Produces: `validate_settlement_record(record: dict[str, Any]) -> None`.
- Produces: `StrategyLedgerStore(data_dir: Path)` with `load(month_text: str) -> list[dict[str, Any]]` and `save(month_text: str, records: list[dict[str, Any]]) -> None`.

- [ ] **Step 1: Write failing formula and validation tests**

```python
from post_market_ledger import calculate_settled_profit, validate_settlement_record

class SettlementTests(unittest.TestCase):
    def test_mode2_passive_assignment_uses_actual_settlement_formula(self):
        record = {
            "mode": "mode2", "strike": 3.10, "stock_shares": 60000,
            "stock_price": 3.09, "option_contracts": 6,
            "option_premium": 201.0, "stock_commission_rate": 0.0002,
        }
        self.assertEqual(calculate_settled_profit(record), 568.92)

    def test_rejects_stock_option_quantity_mismatch(self):
        with self.assertRaisesRegex(ValueError, "10000"):
            validate_settlement_record({"stock_shares": 10000, "option_contracts": 2})
```

Add one exact expected-value test for each of modes 1, 3 and 4. Include mode 1 and 4 buy-open plus active-exercise fees, mode 3 passive zero option fee, and a monthly store round-trip test using `TemporaryDirectory`.

- [ ] **Step 2: Run test to verify failure**

Run: `python -m unittest tests.test_post_market_ledger -v`

Expected: FAIL because `post_market_ledger` does not yet exist.

- [ ] **Step 3: Write minimal implementation**

```python
OPTION_MULTIPLIER = 10000

def calculate_settled_profit(record: dict[str, Any]) -> float:
    validate_settlement_record(record)
    mode = record["mode"]
    shares = float(record["stock_shares"])
    contracts = float(record["option_contracts"])
    strike = float(record["strike"])
    stock = float(record["stock_price"])
    premium = float(record["option_premium"])
    commission = float(record.get("stock_commission_rate", 0.0002))
    buy_fee = float(record.get("option_buy_open_fee", 2.0))
    exercise_fee = float(record.get("active_exercise_fee", 4.0))
    borrow_cost = float(record.get("borrow_cost", 0.0))
    if mode == "mode1":
        result = strike * shares - (stock * shares * (1 + commission) + premium * contracts + buy_fee * contracts + exercise_fee * contracts)
    elif mode == "mode2":
        result = stock * shares * (1 - commission) + premium * contracts - strike * shares
    elif mode == "mode3":
        result = strike * shares + premium * contracts - stock * shares * (1 + commission)
    elif mode == "mode4":
        result = stock * shares * (1 - commission) - (strike * shares + premium * contracts + buy_fee * contracts + exercise_fee * contracts + borrow_cost)
    else:
        raise ValueError("Unsupported strategy mode")
    return round(result, 2)
```

Implement `format_settlement_formula` with substituted values and the calculated total. Implement `StrategyLedgerStore` with strict `YYYY-MM` validation, UTF-8 JSON, an atomic `.tmp` write then `replace`, and a list-only payload check.

- [ ] **Step 4: Run tests to verify success**

Run: `python -m unittest tests.test_post_market_ledger -v`

Expected: PASS for formula, validation, formula text and store round-trip tests.

- [ ] **Step 5: Commit**

```powershell
git add post_market_ledger.py tests/test_post_market_ledger.py
git commit -m "Add settled strategy ledger calculations"
```

### Task 2: Manual Post-Market Ledger Dialog

**Files:**
- Modify: `D:/mycode/50qq/post_market_ledger.py`
- Modify: `D:/mycode/50qq/tests/test_post_market_ledger.py`

**Interfaces:**
- Consumes: `calculate_settled_profit`, `format_settlement_formula`, `validate_settlement_record`, and `StrategyLedgerStore` from Task 1.
- Produces: `StrategyLedgerDialog(config_dir: Path, parent: QWidget | None = None)`.

- [ ] **Step 1: Write a failing dialog behavior test**

```python
class LedgerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_uses_config_directory_for_monthly_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dialog = StrategyLedgerDialog(Path(temp_dir))
            self.assertEqual(dialog.store.data_dir, Path(temp_dir) / "strategy_ledger_data")
            self.assertTrue(dialog.month_total_label.text().startswith("本月已结算"))
```

Add a test asserting mode 2 disables and zeros the buy-open and active-exercise controls.

- [ ] **Step 2: Run dialog test to verify failure**

Run: `python -m unittest tests.test_post_market_ledger -v`

Expected: FAIL because `StrategyLedgerDialog` is not defined.

- [ ] **Step 3: Implement the compact manual dialog**

Create `StrategyLedgerDialog(QDialog)` with:

```python
MODE_LABELS = {
    "mode1": "模式1：买入认沽 + 买入现货",
    "mode2": "模式2：卖出认沽 + 卖出现货",
    "mode3": "模式3：卖出认购 + 买入/持有现货",
    "mode4": "模式4：买入认购 + 卖出现货",
}
```

The form includes settlement date, ETF code, option code, strike, stock shares, actual stock price, option contracts, option premium in yuan per contract, commission, buy-open fee, active-exercise fee, borrow cost and note. On mode change, update price/premium labels and disable plus zero the two option-fee controls for modes 2 and 3. Use defaults `0.0002`, `2.00` and `4.00` for modes 1 and 4.

At the top, show the selected month, record count and `本月已结算利润` as the sum of persisted `result` values. Provide Add/Save, Clear and Delete buttons. The non-editable table must show date, mode, ETF, option code, strike, shares, contracts, stock price, option premium, settled result, formula and note. Selecting a row loads it into the form; saving creates or replaces the record then persists the relevant month.

- [ ] **Step 4: Run dialog and domain tests**

Run: `python -m unittest tests.test_post_market_ledger -v`

Expected: PASS, including the headless dialog construction test.

- [ ] **Step 5: Commit**

```powershell
git add post_market_ledger.py tests/test_post_market_ledger.py
git commit -m "Add post-market strategy ledger dialog"
```

### Task 3: Scanner Entry Point And Windows Package Verification

**Files:**
- Modify: `D:/mycode/50qq/option_arbitrage_scanner.py:1-40`
- Modify: `D:/mycode/50qq/option_arbitrage_scanner.py:2950-2972`
- Modify: `D:/mycode/50qq/option_arbitrage_scanner.py:3668-3718`
- Modify: `D:/mycode/50qq/tests/test_option_arbitrage_scanner.py`

**Interfaces:**
- Consumes: `StrategyLedgerDialog(config_dir: Path, parent: QWidget | None = None)`.
- Produces: `MainWindow.open_post_market_ledger() -> None`.

- [ ] **Step 1: Write a failing scanner entry-point test**

```python
@patch("option_arbitrage_scanner.StrategyLedgerDialog")
@patch.object(MainWindow, "_start_worker")
def test_post_market_button_opens_ledger_beside_config(self, _worker, dialog_class):
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "contracts_config.json"
        window = MainWindow(config_path)
        window.open_post_market_ledger()
        dialog_class.assert_called_once_with(Path(temp_dir), window)
```

Patch the worker start if necessary so this test does not create a QMT thread.

- [ ] **Step 2: Run scanner entry-point test to verify failure**

Run: `python -m unittest tests.test_option_arbitrage_scanner.ExpiryAndMoneynessTests -v`

Expected: FAIL because the dialog import and method do not exist.

- [ ] **Step 3: Add the narrow scanner integration**

Import `StrategyLedgerDialog`, add a compact `盘后计算` toolbar button beside `公式`, and include it in the existing button height/style loop. Add:

```python
def open_post_market_ledger(self) -> None:
    dialog = StrategyLedgerDialog(self.config_path.parent, self)
    dialog.exec()
```

Do not alter `QuoteWorker`, QMT path resolution, fee configuration or any existing opportunity calculation. Preserve the already-present uncommitted exercise-status changes.

- [ ] **Step 4: Run all tests and compile checks**

Run: `python -m unittest discover -v`

Expected: PASS for existing scanner, existing standalone ledger and new post-market ledger tests.

Run: `python -m py_compile option_arbitrage_scanner.py post_market_ledger.py`

Expected: exit code 0.

- [ ] **Step 5: Build and verify customer package**

Run:

```powershell
pyinstaller --noconfirm --clean 50qqScanner.spec
Copy-Item -LiteralPath contracts_config.json -Destination dist\50qqScanner\contracts_config.json -Force
Get-Item dist\50qqScanner\50qqScanner.exe, dist\50qqScanner\contracts_config.json
```

Expected: the scanner executable and root configuration file both exist. The ledger data directory is created only when the user saves the first monthly record.

- [ ] **Step 6: Review staging scope and commit only approved changes**

Run: `git status --short` and inspect the diff before staging. If the existing uncommitted exercise-status edits are not explicitly approved for this commit, leave them unstaged and ask before committing the scanner integration that shares the same file.
