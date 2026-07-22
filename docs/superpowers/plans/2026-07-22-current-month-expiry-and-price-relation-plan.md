# Current-Month Expiry and Price-Relation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict automatic option-chain scanning to the current calendar month and display direct spot-versus-strike relations.

**Architecture:** Keep option moneyness as an internal boolean separate from its user-facing text. The automatic resolver receives the current `YYYYMM` and never retries an unfiltered chain; tables and recommendations render the direct comparison label while retaining their current financial decisions through `is_in_the_money`.

**Tech Stack:** Python 3.10, PyQt6, `unittest`, PyInstaller.

## Global Constraints

- Modify only the expiry resolver and moneyness display paths.
- Do not change option-profit, fee, recommendation, alert, or highlight thresholds.
- Automatic resolution must use `time.strftime("%Y%m")` and must not fall back to all expiry months.
- Keep the Windows bundle output at `dist/50qqScanner/50qqScanner.exe`.

---

### Task 1: Add testable expiry and moneyness helpers

**Files:**
- Create: `tests/test_option_arbitrage_scanner.py`
- Modify: `option_arbitrage_scanner.py:630-645`

**Interfaces:**
- Produces `current_expiry_yyyymm() -> str`.
- Produces `option_is_in_the_money(spot_price: float, strike: float, *, is_call: bool) -> bool`.
- Produces `option_moneyness_text(spot_price: float, strike: float, *, is_call: bool) -> str`.

- [ ] **Step 1: Write the failing test**

```python
@patch("option_arbitrage_scanner.time.strftime", return_value="202607")
def test_current_expiry_month_uses_calendar_month(self, _strftime):
    self.assertEqual(current_expiry_yyyymm(), "202607")

def test_display_uses_direct_price_relation(self):
    self.assertEqual(option_moneyness_text(3.075, 3.10, is_call=False), "现价低于行权价")
    self.assertEqual(option_moneyness_text(3.075, 3.00, is_call=True), "现价高于行权价")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_option_arbitrage_scanner -v`

Expected: import failure because the new helper functions do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def current_expiry_yyyymm() -> str:
    return time.strftime("%Y%m")

def option_is_in_the_money(spot_price: float, strike: float, *, is_call: bool) -> bool:
    return spot_price > strike if is_call else spot_price < strike

def option_moneyness_text(spot_price: float, strike: float, *, is_call: bool) -> str:
    if abs(spot_price - strike) <= 0.001:
        return "现价接近行权价"
    return "现价高于行权价" if spot_price > strike else "现价低于行权价"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_option_arbitrage_scanner -v`

Expected: all helper tests pass.

### Task 2: Restrict automatic chain resolution to the current month

**Files:**
- Modify: `option_arbitrage_scanner.py:1377-1463, 1612-1649`
- Test: `tests/test_option_arbitrage_scanner.py`

**Interfaces:**
- Consumes `current_expiry_yyyymm() -> str`.
- `pick_strike_ladder_for_underlying(..., expiry_yyyymm)` and `pick_atm_for_underlying(..., expiry_yyyymm)` query only the supplied month.

- [ ] **Step 1: Write the failing test**

```python
@patch("option_arbitrage_scanner._gather_option_strike_pairs")
def test_atm_lookup_does_not_retry_all_expiries(self, gather_pairs):
    gather_pairs.return_value = ({}, {}, {})
    self.assertIsNone(pick_atm_for_underlying("510050.SH", 3.075, "202607"))
    self.assertEqual(len(gather_pairs.call_args_list), 1)
    self.assertEqual(gather_pairs.call_args_list[0].args[2], "202607")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_option_arbitrage_scanner.ExpiryAndMoneynessTests.test_atm_lookup_does_not_retry_all_expiries -v`

Expected: FAIL because the resolver makes a second unfiltered lookup.

- [ ] **Step 3: Write minimal implementation**

```python
# In both automatic resolvers:
month_filters = [expiry_yyyymm] if expiry_yyyymm else []
if not month_filters:
    return None  # return [] in the ladder resolver

# When automatic pairs are resolved:
yyyymm = current_expiry_yyyymm()
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `python -m unittest tests.test_option_arbitrage_scanner -v`

Expected: all expiry and moneyness tests pass.

### Task 3: Preserve logic with an internal boolean and update display text

**Files:**
- Modify: `option_arbitrage_scanner.py:1135-1164, 2095-2124, 3519-3533, 3593-3597`
- Test: `tests/test_option_arbitrage_scanner.py`

**Interfaces:**
- Opportunity rows gain `is_in_the_money: bool`.
- Recommendation and conditional upper-profit paths read `is_in_the_money`, not the display text.

- [ ] **Step 1: Write the failing test**

```python
def test_conditional_recommendation_uses_boolean_not_display_text(self):
    row = {
        "profit": -21.10,
        "alert_eligible": False,
        "is_in_the_money": True,
        "moneyness_text": "现价低于行权价",
        "exercise_upper_profit": 39.95,
    }
    self.assertEqual(recommendation_effective_profit(row), 39.95)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_option_arbitrage_scanner -v`

Expected: FAIL because recommendation eligibility compares the retired display text.

- [ ] **Step 3: Write minimal implementation**

```python
is_in_the_money = option_is_in_the_money(spot_mid, pair.strike, is_call=bool(item["is_call"]))

# Store it in each row and replace all current-in-the-money string checks:
"is_in_the_money": is_in_the_money
if bool(row.get("is_in_the_money")) and upper_profit is not None:
    return float(upper_profit)
```

- [ ] **Step 4: Run the full unit suite and compile check**

Run: `python -m unittest tests.test_option_arbitrage_scanner -v; python -m py_compile option_arbitrage_scanner.py`

Expected: all tests pass and compilation exits with code 0.

- [ ] **Step 5: Build the Windows bundle**

Run: `pyinstaller --noconfirm --clean 50qqScanner.spec`

Expected: exit code 0 and `dist/50qqScanner/50qqScanner.exe` exists.

- [ ] **Step 6: Commit**

```bash
git add option_arbitrage_scanner.py tests/test_option_arbitrage_scanner.py && git commit -m "Restrict scans to current expiry month"
```
