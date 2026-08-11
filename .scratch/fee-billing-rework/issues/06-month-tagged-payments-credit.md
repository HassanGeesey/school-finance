# 06 — Month-tagged payments & roll-forward credit

**What to build:** Recording money in against a month. A payment is recorded as (student, month+year tag, amount, method, date) — **any** month can be tagged (FW-16). The tag is the clerk's entry: the record screen surfaces the student's **oldest unpaid month first** and never silently defaults to "this month" (FW-22-1); a tag outside the student's owed range triggers a **warning, not a block** (FW-22-2, e.g. a fat-fingered future month or a closed month). Excess over the month's expected **rolls forward as credit**, consumed by the oldest owed months' shortfalls first (FW-15/FW-21); the account shows how much credit each month consumed. Credit balance carries indefinitely (no refunds in v1). Receipt printed after recording (unchanged).

**UI:** Rework the record-payment screen: search student → live account summary → month picker (defaulted to oldest unpaid owed month) → amount + method → live "expected vs paid vs credit" confirmation → save → toast + print receipt.

**Blocked by:** 01 — Schema reshape, 03 — Enrollment & effective-dated amounts, 04 — Owed months & closed months, 05 — Waivers

**Status:** implemented

- [x] Payment carries a month+year tag; any month recordable
- [x] Oldest unpaid owed month surfaced first on the record screen
- [x] Warning (not block) for out-of-range tagged months
- [x] Excess rolls forward as credit; credit consumed oldest-owed-month-first, visible per month
- [x] Receipt + audit unchanged for payments; credit movements audit/display
- [x] Tests: `tests/test_payments_service.py` (+ routes) reworked for month-tag + credit

## Comments

The month-tag + credit machinery was already built into the derived model when the
rework checkpoint landed (payments service/routes + account derivation); this ticket
locks it in with a test suite, fixes a real balance bug it exposed, and closes the one
UI gap — the record screen now visibly defaults the month tag.

- **Service seam (`PaymentService`, app/payments/service.py):** logic unchanged.
  `record_payment` stores (student, month+year tag, amount, method, date) with **any**
  month recordable (FW-16); it settles the tagged month's shortfall and carries excess
  as a `Credit` row linked to the payment (FW-15); `preview_application` shows the
  live expected/paid/remaining/applied/credit split plus `in_owed_range` (FW-22-2);
  `account_summary` surfaces `oldest_unpaid` as the record screen's default tag
  (FW-22-1). Now pinned by **tests/test_payments_service.py** (17 tests): tagged store,
  shortfall settlement, credit creation, pre-enrollment/future/closed months all
  recordable (out-of-range → full credit), preview write-nothing + warning + already-
  tagged awareness + invalid-amount rejection, credit consumed oldest-owed-month-first
  with per-month amounts on the account, balance = expected − received, `oldest_unpaid`
  progression, audit entry content (`period_label`, "applied"/"excess" summary lines),
  and rejected payments writing no Payment/Credit/audit rows.
- **Balance fix (app/fees/account.py):** `AccountView.balance_cents` was
  `expected − paid − credits`, double-counting credit when a payment exceeded a
  month's expected (a $60 payment against a $50 month read −$20 instead of −$10).
  Now `expected − received` — every dollar either settles expected or is held as
  credit. Arrears numbers derive from this the same way, so app/arrears/service.py
  docstrings were corrected to "expected minus received".
- **Record screen default (FW-22-1):** split-screen month/year pickers were blank
  until submit, so the clerk couldn't see the default tag. New GET
  `/payments/period-selects` fragment (payments/_period_selects.html) is swapped into
  the form (`#payment-period`, triggered on student selection) pre-selecting the
  oldest unpaid owed month; year options widened to last→+2 years so back-dated tags
  are pickable. 404s for a missing student.
- **Routes tests (tests/test_payments_routes.py, +6):** record form defaults the tag
  to the oldest unpaid month; period-selects fragment defaults / blanks without a
  student / 404s; an out-of-range tag shows the preview warning but still records
  (warn, not block); overpayment balance on the account page shows −$10.00.
- **Receipt + audit unchanged:** receipt (applied + credit-on-account lines) and the
  payment audit entry were already correct; covered by the service audit test.
- **Verification:** `python -m pytest tests/` → **602 passed** (was 579; +17 service,
  +6 route tests). mypy clean on changed modules; the only reported error
  (students/routes.py:218) is pre-existing.

Commit: TBD
