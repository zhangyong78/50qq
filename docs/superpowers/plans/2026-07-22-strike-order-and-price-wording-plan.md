# Strike Order and Price Wording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render every mode table in ascending strike-price order and show the strike relative to spot price.

**Architecture:** Add one pure row-order helper so table ordering can be tested without constructing a PyQt window. Keep the existing option in-the-money boolean and recommendation ordering unchanged; only the displayed status string changes.

**Tech Stack:** Python 3.10, PyQt6, `unittest`, PyInstaller.

## Global Constraints

- Default table order is numeric `strike` ascending with option code as a stable secondary key.
- Display only `行权价低于现价`, `行权价高于现价`, and `行权价接近现价` for valid prices.
- Do not change recommendation ordering, option moneyness, fees, profit, alerts, or thresholds.
- Keep the Windows bundle output at `dist/50qqScanner/50qqScanner.exe`.

---

### Task 1: Add testable strike ordering and wording

**Files:**
- Modify: `tests/test_option_arbitrage_scanner.py`
- Modify: `option_arbitrage_scanner.py:1124-1145`

**Interfaces:**
- Produces `sort_mode_rows_by_strike(rows: list[dict[str, Any]]) -> list[dict[str, Any]]`.
- `option_moneyness_text(...) -> str` returns the new display terms.

- [ ] **Step 1: Write the failing tests**

```python
def test_mode_rows_sort_by_numeric_strike_then_option_code(self):
    rows = [
        {"strike": 3.20, "option_code": "B.SH"},
        {"strike": 3.00, "option_code": "C.SH"},
        {"strike": 3.20, "option_code": "A.SH"},
    ]
    self.assertEqual(
        [row["option_code"] for row in sort_mode_rows_by_strike(rows)],
        ["C.SH", "A.SH", "B.SH"],
    )

def test_display_describes_strike_relative_to_spot(self):
    self.assertEqual(option_moneyness_text(3.075, 3.10, is_call=False), "行权价高于现价")
    self.assertEqual(option_moneyness_text(3.075, 3.00, is_call=True), "行权价低于现价")
    self.assertEqual(option_moneyness_text(3.075, 3.0754, is_call=True), "行权价接近现价")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_option_arbitrage_scanner -v`

Expected: import failure for `sort_mode_rows_by_strike` and wording assertion failures.

- [ ] **Step 3: Write minimal implementation**

```python
def sort_mode_rows_by_strike(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (float(row.get("strike", 0.0)), str(row.get("option_code", ""))))

def option_moneyness_text(spot_price: float, strike: float, *, is_call: bool) -> str:
    if spot_price <= 0 or strike <= 0:
        return "价格未知"
    if abs(spot_price - strike) <= 0.001:
        return "行权价接近现价"
    return "行权价低于现价" if strike < spot_price else "行权价高于现价"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_option_arbitrage_scanner -v`

Expected: all tests pass.

### Task 2: Use strike ordering in all mode tables and package

**Files:**
- Modify: `option_arbitrage_scanner.py:3470-3481`
- Test: `tests/test_option_arbitrage_scanner.py`

**Interfaces:**
- `_rows_for_mode(...)` uses `sort_mode_rows_by_strike(filtered)`.

- [ ] **Step 1: Replace the table-only sort**

```python
filtered = [row for row in self._display_filtered_rows(rows) if row.get("mode_key") == mode_key]
return sort_mode_rows_by_strike(filtered)
```

- [ ] **Step 2: Verify source, tests, and package**

Run: `python -m unittest tests.test_option_arbitrage_scanner -v; python -m py_compile option_arbitrage_scanner.py; pyinstaller --noconfirm --clean 50qqScanner.spec`

Expected: tests and compilation pass; `dist/50qqScanner/50qqScanner.exe` exists.

- [ ] **Step 3: Commit**

```bash
git add option_arbitrage_scanner.py tests/test_option_arbitrage_scanner.py docs/superpowers/plans/2026-07-22-strike-order-and-price-wording-plan.md && git commit -m "Sort mode rows by strike price"
```
