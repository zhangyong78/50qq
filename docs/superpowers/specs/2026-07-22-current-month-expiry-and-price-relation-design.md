# Current-Month Expiry and Price-Relation Display

## Goal

Only scan option contracts expiring in the current calendar month. Replace the
ambiguous display labels `当前价内` and `当前价外` with a direct comparison
between the current ETF price and the strike price.

## Scope

- The automatic ATM and strike-ladder resolvers use the current `YYYYMM` month.
- They do not retry with an unrestricted all-expiry scan when the current month
  has no matching contracts.
- A missing current-month chain leaves the existing no-contract status visible
  instead of showing a later expiry.
- Table and recommendation text display one of: `现价低于行权价`,
  `现价高于行权价`, or `现价接近行权价`.

## Internal Behaviour

The application keeps an internal `is_in_the_money` boolean. The definition
remains option-specific: calls are in the money when spot is above strike, and
puts are in the money when spot is below strike. Recommendation eligibility,
conditional-profit highlighting, and all profit formulas use this boolean, so
their financial logic does not depend on the user-facing wording.

## Validation

- Unit checks cover current-month selection, no far-month fallback, and the
  direct price-relation labels for calls, puts, and near-strike prices.
- The module compiles successfully.
- The Windows executable is rebuilt after the code checks pass.
