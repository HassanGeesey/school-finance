# 03 — Enrollment & effective-dated amounts

**What to build:** Enrollment carries the billing start, and a student's monthly amount is effective-dated. When adding a student (manual or CSV import), the clerk records `enrolled_on` (default today, back-datable) and picks a linked template or a custom monthly amount. Archiving captures `archived_on` (the leaving month's charge stays — service-through-period-end, FW-14). A per-student amount change carries an effective month (default next month); a month's expected uses the amount in force for that month (FW-20). Template raises (ticket 02) add an amount-change entry to each linked student's schedule.

**UI:** Extend the add/import student form with enrolled-on + template/custom-amount fields; the class default template pre-fills. Student edit gains "change monthly amount (effective from month)". Archive dialog records the date.

**Blocked by:** 01 — Schema reshape, 02 — Fee templates & class defaults

**Status:** implemented

- [x] `enrolled_on` on add and CSV import (default today, editable)
- [x] `archived_on` captured when archiving; leaving month still owed
- [x] Student linked to a template or holds a custom amount
- [x] Amount-in-force resolution per month (effective-dated changes)
- [x] Amount changes audited
- [x] Tests: `tests/test_students_service.py`, `tests/test_students_routes.py`, fee amount resolution tests

## Comments

Implemented alongside the fee-billing rework commit.

- **Add/import billing fields:** `add_student`/`import_students_csv` take `enrolled_on` (default today, back-datable), `fee_template_id`, `custom_amount`. The add/import forms carry enrolled-on + template/custom-amount inputs, pre-filled with the class default template (`_class_default_template_id`). Custom amount wins over a picked template; missing both falls back to the class default.
- **Archive:** `archive_student` sets `archived_on`; `owed_months` runs the enrollment month through the archived month (leaving month still owed, service-through-period-end FW-14).
- **Effective-dated amounts:** `app/fees/account.py` `amount_in_force` resolves the latest `StudentAmountChange` on/before the month (else the linked template's current amount); `expected_cents`/`month_comparison`/`student_account` build the per-month expected from it. `change_amount` (unlinks template, FW-19) and `set_template` seed the new amount effective from a chosen month, defaulting to next month (`default_effective_month`, FW-20).
- **Edit-amount UI:** `students/edit.html` now shows the current amount and a change block (template picker / custom amount + effective-month select, default next month); the edit route applies it via `_apply_billing_change` (names-only edits make no billing change, no audit noise). Rejects invalid effective months ("Choose a valid effective month.") and non-positive amounts.
- **Audit:** amount changes log `STUDENT_AMOUNT_CHANGE`, template links log `STUDENT_TEMPLATE`.
- **Fixed a period-order bug while making the /students page green:** `owed_months` returned `(year, month)` while its four callers (and the closed-month filter) assume `(month, year)` — the closed-month exclusion never matched and the status filter/paid-students helpers could not match an owed month. `owed_months`/`month_range` now return `(month, year)`; the three period-dropdown consumers (`reports/routes.py`, `students/routes.py` search page, and the expense-period insert in `reports/service.py.list_periods`) were updated to unpack `(month, year)`. Also fixed `class_detail` not rendering the `?err=` param that `add_student` redirects with.
- **Verification:** `python -m pytest tests/` — 700 passed, exit 0. `tests/test_students_routes.py` rewritten for the derived-billing flow (no legacy `generate_fees`/`add_fee_item`), plus new edit-amount route tests (change amount, link template, audit, invalid month/amount).
- **Commit:** committed as part of the fee-billing rework landing.

