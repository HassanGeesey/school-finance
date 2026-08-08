# 20 — One payment-allocation planner

**What to build:** The clearing rule — payments applied to the oldest unpaid charges first, partial application, excess becomes credit — lives in exactly one callable in the payment module. Recording, previewing, and the arrears/reports views that need per-charge allocation all call it. Changing the rule changes one function.

**Blocked by:** None — can start immediately

**Status:** implemented

- [x] One allocation function computes per-charge applied amounts + credit for a given amount
- [x] `record_payment` and `preview_application` both clear through it; behaviour is identical (oldest-first, partials, overpayment → credit)
- [x] The paid-cents grouping duplicated in reports and arrears reuses the same planner
- [x] Tests cover the planner once; existing payment/arrears/report tests stay green

## Comments

Implemented 2026-08-08. New module `app/payments/planner.py` owns the clearing rule. `plan_application(charges, paid_cents, amount_cents)` is the single allocation callable — oldest period first, partials, overpayment → credit — and `paid_cents_by_charge(session, charge_ids=None)` is the single paid-cents grouping query. `PaymentService.record_payment` and `preview_application` now both clear through `plan_application` (identical behaviour, unchanged outputs), and the account view plus reports and arrears all read the same grouping instead of their three private `_paid_cents_by_charge` copies. Removed the join-based student variant in payments and the `.in_`/all-rows variants in reports/arrears (~90 lines of duplication).

Verification:
- 671 tests pass (full suite), `mypy app` clean on 50 source files.
- New `tests/test_payments_planner.py` covers the planner once: pure `plan_application` cases (oldest-first, partial, credit, skips settled, net-of-adjustments, waived-to-zero, no charges) and session-based `paid_cents_by_charge` grouping (sum, id filter, empty filter, unfiltered). Existing payment/arrears/report service + route tests unchanged and green.

Commit: 8addc29
