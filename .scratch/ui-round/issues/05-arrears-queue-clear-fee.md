# 05 — Arrears queue + clear-fee wiring

**What to build:** The unpaid-fees page becomes prototype view 3: a prioritized per-Campus queue of outstanding student balances. Panel header carries the total-unpaid badge; the ledger table shows student with family-account line, class, overdue-month badges, guardian contact, urgency badge (urgent amber / reminder slate), and balance due right-aligned bold in rose. Row actions: Clear Fee opens the payment modal pre-filled with that student and balance (ticket 04); any communication actions (SMS/reminders) are omitted — no backend exists, no dead buttons. Balances stay derived from services (Expected Amount minus waivers/payments), never computed in templates.

**Blocked by:** 04 — Record Payment modal + live allocation slip.

**Status:** implemented

- [x] Queue renders per campus with urgency badges and correct derived balances
- [x] Clear Fee pre-fills and opens the modal for the right student/amount
- [x] Settling via the modal removes/updates the row as today's flow does
- [x] No dead controls shipped
- [x] Arrears route tests pass unchanged

## Comments

Built (commit `052f67b`): unpaid-fees page rebuilt as prototype view 3 — panel header with total-unpaid badge; ledger rows: student + family-account line, class, overdue-month badges, urgency badge (urgent amber / reminder slate), balance due right-aligned bold rose `.num`. Row "Clear Fee" includes the ticket-04 `payments/_record_modal.html` (record_students built from the page's service-derived lines); each row's button carries data-clear-fee/data-modal-open plus data-clear-student/amount; a capture-phase inline script prefills student/amount (defaults paid-on to today, dispatches input/change so the live slip re-renders) before ui.js opens the dialog. Month/year intentionally post blank exactly like the classic flow so the endpoint tags FW-22-1 oldest-unpaid and lands on the receipt — rows update on return as today. SMS/reminder/batch/export controls omitted entirely (no backend).

Foundation gaps (honest omissions, both need model/context work outside round scope): (1) guardian contact column — Student model has no guardian fields; (2) per-campus name badge — route context lacks campus name at render time (queue is already auth-scoped per campus).

Verification: test_arrears_routes + test_arrears_service = 17 passed, tests untouched.
