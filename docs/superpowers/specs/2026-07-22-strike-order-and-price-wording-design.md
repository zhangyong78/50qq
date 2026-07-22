# Strike Order and Price Wording

## Goal

Show every mode table in ascending numeric strike-price order and use wording
that describes the strike relative to the current price.

## Scope

- Default rows in each mode table sort by `strike` ascending.
- When strikes match, the option code provides deterministic secondary order.
- The current-status column uses `行权价低于现价`, `行权价高于现价`, or
  `行权价接近现价`.
- The recommendation panels keep their existing profitability order.
- In-the-money calculations, fees, profit formulas, highlights, and alerts do
  not change.

## Validation

- Unit checks cover ascending numeric strike ordering and all three display
  labels.
- Existing unit tests, module compilation, and the Windows package build pass.
