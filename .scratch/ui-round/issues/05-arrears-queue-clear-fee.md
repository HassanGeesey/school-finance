# 05 — Arrears queue + clear-fee wiring

**What to build:** The unpaid-fees page becomes prototype view 3: a prioritized per-Campus queue of outstanding student balances. Panel header carries the total-unpaid badge; the ledger table shows student with family-account line, class, overdue-month badges, guardian contact, urgency badge (urgent amber / reminder slate), and balance due right-aligned bold in rose. Row actions: Clear Fee opens the payment modal pre-filled with that student and balance (ticket 04); any communication actions (SMS/reminders) are omitted — no backend exists, no dead buttons. Balances stay derived from services (Expected Amount minus waivers/payments), never computed in templates.

**Blocked by:** 04 — Record Payment modal + live allocation slip.

**Status:** ready-for-agent

- [ ] Queue renders per campus with urgency badges and correct derived balances
- [ ] Clear Fee pre-fills and opens the modal for the right student/amount
- [ ] Settling via the modal removes/updates the row as today's flow does
- [ ] No dead controls shipped
- [ ] Arrears route tests pass unchanged

## Comments

-
