# Trade Ledger Design

## Goal

Provide an independent Windows desktop ledger for recording ETF spot and option
trades, then calculating the selected day's cash-flow net profit.

## Application

- Program name: `ETF期权交易小账本`.
- Separate PyQt6 executable named `TradeLedger.exe`.
- No QMT, market-data, or scanner dependency.

## Records

Each record contains date, instrument type (`现货` or `期权`), direction
(`买入` or `卖出`), code, price, quantity, fee, and note.

- Spot gross amount is `price * quantity`.
- Option gross amount is `price * quantity * 10000`.
- Daily net profit is total sell gross amount minus total buy gross amount minus
  total fee.

## Interface

- The top summary shows selected date, buy amount, sell amount, fee, and net
  profit with positive and negative color cues.
- The entry form defaults to today's date and supports adding records.
- The record table supports selecting a row for edit or deletion.
- Changing the date loads that day's records and recalculates the summary.

## Storage

- Store data locally in `ledger_data/YYYY-MM-DD.json` beside the program.
- Save after every add, edit, or deletion.
- Invalid or absent files result in an empty ledger and a visible error message;
  valid existing records remain untouched.

## Out Of Scope

- No position cost, unrealized profit, automatic fee calculation, QMT import,
  cloud synchronization, or monthly reports in this first version.

## Validation

- Unit tests cover gross amount and daily cash-flow calculation for spot and
  option trades, plus JSON load and save round trips.
- The module compiles and the standalone executable builds successfully.
