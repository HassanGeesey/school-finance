# 05 — Waivers (charge forgiveness)

**What to build:** Per (student, month) forgiveness. A waiver reduces that month's expected amount by a given amount, floored at $0; multiple waivers stack; a reason/label is required (FW-11). Recordable by Admin **and** Finance officer (FW-13). Waiving a month in full means the student owes $0 for it (used for trivial mid-month partials and skipped months not covered by the closed-month list). Waivers are the only per-month record in the model — no "extras" (FW-12).

**UI:** On the student account page (or via the student), an "Add waiver" action: month picker (pre-filled with an owed month), amount, reason. Waivers list against the month, shown in the account history. Confirmation on create; toast on success.

**Blocked by:** 01 — Schema reshape, 03 — Enrollment & effective-dated amounts, 04 — Owed months & closed months

**Status:** implemented

- [x] Add a waiver (student, month, amount, reason) — amount > 0, expected never below $0
- [x] Multiple waivers stack on a month
- [x] Reason required; creation audited (who + why)
- [x] Both Admin and Finance officer can waive
- [x] Tests: `tests/test_adjustments_service.py` reworked → waiver service tests (+ routes)

## Comments

Implemented with WaiverService + account-page UI.

- **Service:** `WaiverService.add_waiver` (app/fees/service.py) — validates student/month/year/amount (positive decimal)/reason (non-blank), stores the waiver, audits `WAIVER_ADD` with who+why (label, amount, period in summary). Stacking drops the unique constraint on (student, month, year) from `app/models.py`.
- **Derivation:** `waivers_for_month` + `expected_cents` in app/fees/account.py — expected is floored at $0 when stacked waivers exceed the monthly expected amount (FW-10).
- **Routes (app/students/routes.py):** `require_login` only (Admin + Finance, FW-13); GET `_waiver_form.html` into a modal, POST with htmx `HX-Trigger` (toast + `waivers-changed`) or plain 303 redirect; `WaiverError` → 400 re-render. Shared `_account_context` + `GET /account/finance` partial for htmx refresh.
- **UI:** "Add waiver" button on `students/account.html`; waiver history per month on `fees/_account_finance.html`.
- **Tests:** `tests/test_waivers_service.py` (12) — stacking, floor, validation, audit, Finance-officer gate; `tests/test_waivers_routes.py` (13) — form/render/create, htmx + plain, permissions, errors, account history; `tests/test_schema.py` updated for stacked waivers.
- **Verification:** full `pytest tests/` green (waivers + closed-months suites), mypy clean except pre-existing `app/students/routes.py:218` `fee_template_id` arg-type (present on clean HEAD).
- **Note:** this commit also includes the concurrent ticket-04 `fees_closed` wiring in `app/main.py` (single shared file, per session decision).
