# 04 — Record Payment modal + live allocation slip

**What to build:** The record-payment flow becomes prototype's compact modal. Fields: campus (selectable for school-scope users, fixed for campus staff), student select showing monthly rate, integer-cents amount input, target Owed Month select with overdue months marked, payment method select. Below the inputs, a live monospace receipt slip updates as fields change: campus/school header, student, Monthly Amount in force, amount paid, a Credit-rolled-forward row in indigo when overpaying, and a status line — Cleared in full / Partial payment with remaining / Paid in full + credit forwarded. Confirm runs the existing record-payment backend untouched (Month-tagged Payment, Credit rules identical) and surfaces the existing receipt/print outcome; Esc closes without submitting. The modal is openable from any surface that records payments today.

**Blocked by:** 01 — Token layer, component set, app shell.

**Status:** ready-for-agent

- [ ] Slip previews partial-remaining, cleared, and credit-forwarded states correctly for chosen student/amount
- [ ] Submitted payments hit the existing endpoints; amounts, tagged month, method persist exactly as before
- [ ] Receipt generation/print behavior unchanged
- [ ] Esc cancels cleanly; no submission on close
- [ ] Existing payment route tests pass unchanged

## Comments

-
