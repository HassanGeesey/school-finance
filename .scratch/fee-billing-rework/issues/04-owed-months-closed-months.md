# 04 — Owed months & closed months

**What to build:** The derived month range that everything compares against. For a student, owed months run from the `enrolled_on` month through the `archived_on` month (inclusive), skipping **closed months**, while the student is active (FW-14). **Closed months** are a school-wide list (month + year, unique) maintained by the Admin; a closed month is excluded from every student's owed months, carries no expected amount, and never appears as unpaid (FW-17). This derivation is the single seam used by the account view, payments, and reports.

**UI:** A small "Closed months" manager (e.g. under Settings or the Fees/Templates page): add/remove a closed month. The student account and paid/unpaid views simply never show closed months.

**Blocked by:** 01 — Schema reshape, 03 — Enrollment & effective-dated amounts

**Status:** implemented

- [x] Owed-month derivation (enrolled → archived, active only, closed months excluded)
- [x] Archived students: owed months stop at the archive month
- [x] Closed months: add/remove, unique per month+year
- [x] Closed months audited
- [x] Tests: owed-range derivation + closed-month exclusion (service-level)

## Comments

Implemented for the fee-billing rework.

- **Derivation seam:** `app/fees/account.py` — `owed_months` runs from the `enrolled_on` month through the `archived_on` month (service-through-period-end, FW-14) or the current month while active, skipping `ClosedMonth` rows (FW-17); `month_range` and `is_in_owed_range` pin the range math. This was already the seam the account view, payments, arrears, and reports derive from — this ticket locks it with tests and adds the missing manager UI.
- **Closed-month manager (UI):** a "Closed months" card on the `/fees` page (ticket's suggested Fees/Templates placement). Add form (month/year selects) and per-row Reopen action, Admin-only, over htmx with toast; the card owns its `id` and swaps itself in place on every add/remove (plain-request fallback redirects to `/fees` with `msg`/`err`).
- **Routes:** `app/fees/routes.py` — `GET /fees/closed-months/list` (any logged-in user), `POST /fees/closed-months` and `POST /fees/closed-months/remove` (Admin-only). Both mutations validate through the service's public seam; errors (duplicate month, invalid period, not-closed remove) render inline or redirect with `err`. A code-review pass replaced the add-route-only `_validate_period` call in the remove route with service-level validation, and dropped a dead `closed-months-changed` refresh event (the card re-renders itself).
- **Wiring:** `ClosedMonthService` added to the app (`app/main.py` → `app.state.fees_closed`); it was previously built in the service layer but unreachable.
- **Tests:** `tests/test_fees_account.py` (new — `month_range`, `owed_months` active/archived/closed-exclusion, `is_in_owed_range`); `tests/test_fees_service.py` (ClosedMonthService add/remove/unique/audit/list/order); `tests/test_fees_routes.py` (page section, list partial, add/remove via htmx + plain redirect, admin-only enforcement, duplicate and invalid-period errors).
- **Note on "remove" being a hard delete:** the repo's no-hard-deletes rule (models.py) is a deliberate exception here — the ticket says "add/remove a closed month", ticket 01's `ClosedMonth` model carries no status flag, and the list is configuration, not history. Noted as a judgement call in code review.
- **Verification:** `python -m pytest tests/` — 579 passed, exit 0. `mypy app` reports one pre-existing error in `app/students/routes.py` (present at HEAD; this ticket's files are clean).
- **Note:** a concurrent session was editing the same tree (ticket 05 — waivers). Per user instruction the commit stages only ticket 04 files; `app/main.py` unavoidably also carries the waiver session's two `app.state.waivers` wiring lines.
- **Commit:** (see git log for this ticket's commit hash).
