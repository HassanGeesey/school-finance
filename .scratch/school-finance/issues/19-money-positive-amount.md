# 19 — Money module gains the positive-amount rule

**What to build:** All amount validation happens in one place in the money module, so no service re-implements the "must be a positive amount" rule. Each service keeps only its own error translation.

**Blocked by:** None — can start immediately

**Status:** implemented

- [x] The money module exposes a single parse that both converts to integer cents and rejects non-positive amounts
- [x] classes, expenses, fees, and payments all validate incoming amounts through it; no service re-implements the positivity check
- [x] Each service still raises its own domain error with the right message
- [x] Existing tests pass; new tests cover the shared rule once, and each service's translation

## Comments

Implemented 2026-08-08. `app/money.py` now exposes `parse_positive_cents` — the single amount rule — converting any `AmountInput` to positive integer cents (half-up) and raising `InvalidAmount` for unparsable input (incl. non-finite `Infinity`/`NaN` and bools) or `NonPositiveAmount` for zero/negative amounts. The four services (`classes`, `expenses`, `fees`/AdjustmentsService, `payments`) route their `_validate_amount` through it and only translate the two exceptions into their own domain errors with the same messages as before; no service re-implements the `<= 0` check (`to_cents` remains the internal conversion primitive).

Verification:
- 602 tests pass (full suite), `mypy app` clean on 49 source files.
- New tests: `parse_positive_cents` shared rule once in `test_money.py`; per-service translation asserted in `test_classes_service`, `test_expenses_service`, `test_adjustments_service`, `test_payments_service` (including the `preview_application` entry point).

Commit: 2d28158
