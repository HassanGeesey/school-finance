# 07 — Student account view (per-month comparison)

**What to build:** The account page renders the derived comparison. For every owed month (ticket 04): **expected** (amount in force − waivers, min $0), **payments tagged to the month**, **credit consumed**, and a paid/partial/unpaid status. Plus the running totals: total expected, total paid, credit balance, and the outstanding balance (expected − paid − credit, may be negative). Credit application per month is visible (FW-21). This replaces the old charges-with-adjustments account view.

**UI:** Rework the student account page (header with balance, monthly table: month | expected | waivers | paid | credit | status badge, payments list, credits line, balance footer). Actions: record payment (ticket 06), add waiver (ticket 05), change amount (ticket 03). Print statement shows the same per-month breakdown.

**Blocked by:** 04 — Owed months & closed months, 05 — Waivers, 06 — Month-tagged payments & credit

**Status:** ready-for-agent

- [ ] Per-month rows: expected, waivers, paid, credit consumed, status
- [ ] Totals: expected, paid, credit balance, outstanding balance
- [ ] Statement prints the per-month breakdown
- [ ] Tests: account assembly service tests (+ route tests)

## Comments
