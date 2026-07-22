# Integrated Post-Market Ledger Design

## Goal

Add a manual post-market strategy ledger to the existing scanner. One
`50qqScanner.exe` must provide both the intraday opportunity scan and the
monthly settled-profit calculation. The ledger must not depend on QMT quotes
or the scanner's live connection.

## Entry Point

- Add a `盘后计算` button to the scanner toolbar.
- The button opens a `StrategyLedgerDialog` in the same process.
- Keep the existing standalone `TradeLedger` source in the repository, but it
  is not required in the customer delivery folder.
- Store all ledger data in one `strategy_ledger.json` file beside
  `contracts_config.json` so packaged and source launches use a predictable
  location.

## Manual Record

Each record is entered manually and represents an option position that has
already settled through exercise or assignment. It stores:

- settlement date, ETF/spot code, option code, strategy mode, strike and note;
- stock shares and actual stock execution price;
- option contracts and actual premium in yuan per contract;
- stock commission rate, option buy-open fee, active-exercise fee and any
  financing/borrow cost.

The dialog validates that stock shares equal option contracts multiplied by
10,000. It updates field labels by strategy mode so the user sees whether the
stock transaction is a buy or sell and whether the option is a call or put.

## Settled Profit Formulas

All results are actual settled results rather than scanner estimates. Let
`S` be shares, `C` contracts, `K` strike, `P` stock execution price, `Q`
option premium in yuan per contract and `r` the stock commission rate.

| Mode | Formula |
| --- | --- |
| 1: buy put plus buy spot | `K*S - [P*S*(1+r) + Q*C + buy_open_fee*C + active_exercise_fee*C]` |
| 2: sell put plus sell spot | `P*S*(1-r) + Q*C - K*S` |
| 3: sell call plus hold/buy spot | `K*S + Q*C - P*S*(1+r)` |
| 4: buy call plus sell spot | `P*S*(1-r) - [K*S + Q*C + buy_open_fee*C + active_exercise_fee*C + borrow_cost]` |

Modes 2 and 3 are passive assignment/exercise. They do not charge option
open or exercise fees. Defaults for modes 1 and 4 are stock commission
`0.0002`, buy-open fee `2` yuan per contract and active-exercise fee `4`
yuan per contract.

## Interface And Data

- Show the selected month, number of records and monthly settled profit at the
  top of the dialog.
- Provide an add/update form and a table with formula text for each saved
  record, so every result remains auditable.
- Selecting a table row loads it for editing; deletion is explicit.
- Save every record in the single `strategy_ledger.json` file. The interface
  filters and totals records by the selected month without splitting files.
- Persist all input values, formula text and calculated result as a snapshot;
  later fee-default changes must not alter historical monthly results.

## Verification

- Unit-test all four settlement formulas, share/contract validation and JSON
  monthly storage.
- Run the complete unit-test suite and compile check.
- Rebuild `50qqScanner.exe` and copy `contracts_config.json` into the package
  root with the executable.
