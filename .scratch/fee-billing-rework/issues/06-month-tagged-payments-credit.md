# 06 — Month-tagged payments & roll-forward credit

**What to build:** Recording money in against a month. A payment is recorded as (student, month+year tag, amount, method, date) — **any** month can be tagged (FW-16). The tag is the clerk's entry: the record screen surfaces the student's **oldest unpaid month first** and never silently defaults to "this month" (FW-22-1); a tag outside the student's owed range triggers a **warning, not a block** (FW-22-2, e.g. a fat-fingered future month or a closed month). Excess over the month's expected **rolls forward as credit**, consumed by the oldest owed months' shortfalls first (FW-15/FW-21); the account shows how much credit each month consumed. Credit balance carries indefinitely (no refunds in v1). Receipt printed after recording (unchanged).

**UI:** Rework the record-payment screen: search student → live account summary → month picker (defaulted to oldest unpaid owed month) → amount + method → live "expected vs paid vs credit" confirmation → save → toast + print receipt.

**Blocked by:** 01 — Schema reshape, 03 — Enrollment & effective-dated amounts, 04 — Owed months & closed months, 05 — Waivers

**Status:** ready-for-agent

- [ ] Payment carries a month+year tag; any month recordable
- [ ] Oldest unpaid owed month surfaced first on the record screen
- [ ] Warning (not block) for out-of-range tagged months
- [ ] Excess rolls forward as credit; credit consumed oldest-owed-month-first, visible per month
- [ ] Receipt + audit unchanged for payments; credit movements audit/display
- [ ] Tests: `tests/test_payments_service.py` (+ routes) reworked for month-tag + credit

## Comments
