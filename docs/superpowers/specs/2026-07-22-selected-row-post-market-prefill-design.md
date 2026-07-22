# Selected Scan Row To Post-Market Ledger Design

## Goal

Allow the user to select one opportunity row in any scanner mode table and
open the existing post-market ledger with that opportunity prefilled. The
ledger remains editable before the user adds the actual settled record.

## Interaction

- Keep the existing 盘后计算 toolbar button.
- With no selected opportunity row, it opens the empty manual ledger as it
  does today.
- With one selected opportunity row, it opens the ledger with one unsaved
  form prefill. The user can change prices, shares, contracts, fees and note,
  then click 新增记录.
- Keep table double-click unchanged because it is already bound to screen
  freeze/unfreeze.

## Prefill Mapping

| Scanner mode | Ledger mode | Spot default | Option default |
| --- | --- | --- | --- |
| Mode 1, buy put plus buy spot | mode1 | spot ask (buy) | put ask times 10,000 |
| Mode 2, sell put plus sell spot | mode2 | spot bid (sell) | put bid times 10,000 |
| Mode 3, sell call plus buy/hold spot | mode3 | spot ask (buy) | call bid times 10,000 |
| Mode 4, buy call plus sell spot | mode4 | spot bid (sell) | call ask times 10,000 |

The selected row also supplies ETF pool name/code, option code and strike.
The default quantity is one contract and 10,000 spot shares. The existing
mode change behavior continues to set option fees to zero for modes 2 and 3.

## Architecture

- Add a small pure helper in the scanner that finds the selected row from
  mode_tables and its matching rendered_rows_by_mode list.
- Add a small prefill method to StrategyLedgerDialog. It updates widgets
  only; it does not calculate or save a record.
- Extend open_post_market_ledger to pass the selected-row prefill if one is
  available.

## Verification

- Test the scanner mapping for a selected Mode 2 row: mode, ETF code, option
  code, strike, spot bid and option bid times 10,000.
- Test that the dialog displays a supplied prefill and keeps 新增记录 as the
  action, not an automatic save.
- Keep all records in the single `strategy_ledger.json` file beside
  `contracts_config.json`; monthly totals are an interface filter.
- Run the full test suite, compile check and rebuild the Windows executable.
