# 07 — Adjustments

**What to build:** Admin-only per-student month adjustments: add an extra fee item to a student's month, or apply a waiver/discount reducing the charge. Adjustments appear on the student's account and are audited. Finance officer cannot make adjustments.

**UI:** Build on the design system from **05b** — use shared components; adjustments edit via a modal with a toast on save.

**Blocked by:** 06 — Monthly fee generation, 05b — UI design system & app shell

**Status:** implemented

- [x] Admin can add an extra item to a student's month (increases their charge)
- [x] Admin can apply a waiver/discount to a student's month (decreases their charge)
- [x] Adjustments reflect on the student's balance immediately
- [x] Adjustments are visible in the audit log
- [x] Finance officer cannot adjust charges

## Comments

Implemented on 2026-08-05. Business rules live in
`app/fees/service.py` (`AdjustmentsService`): `add_extra()` and
`apply_waiver()` attach an `Adjustment` row to a `Charge`. The net charge is
computed live as base + extras - waivers (`list_student_charges()`,
`student_balance()`), so adjustments reflect on the balance immediately and are
never applied to history. A waiver is capped at the live net — it can clear a
charge exactly but never drive it below zero (`AdjustmentError`). Labels are
required and amounts must be positive money. Every accepted adjustment is
audited under `ADJUSTMENT_ADD`; a rejected one writes nothing. Routes
(`app/fees/account_routes.py`) are thin HTMX adapters: `/students/{id}/account`
(the account page with balance + per-month charges), `/charges/{id}/adjust-form`
(the modal partial), and `/charges/{id}/adjust` (swaps the finance section +
toast). Adjustments are Admin-only — Finance officers can view the account but
the adjust form and POST return 403. Student names now link to their account
from the class detail and student search pages. Verified by the full suite
(service + route tests) and mypy.

Commit: `7b6422c`
