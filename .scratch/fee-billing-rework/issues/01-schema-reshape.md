# 01 — Schema reshape for the compare model

**What to build:** Replace the charge-based billing schema with the derived model. In `app/models.py`: drop `Charge`, `Adjustment`, `GenerationRecord`, `FeeItem`, `PaymentAllocation`; add `FeeTemplate` (name, amount_cents), `Waiver` (student_id, month, year, amount_cents, label, created_by, created_at), `ClosedMonth` (month, year, unique), `Student.enrolled_on` (Date, default today) and `Student.archived_on` (Date, nullable), and `Payment.month` / `Payment.year` (Integer, the month tag). `Credit` stays. Unique constraint on `(student_id, month, year)` for waivers. No data migration — the DB is effectively empty (FW-18).

**Blocked by:** —

**Status:** implemented

- [x] Old tables removed from the model; new tables/columns added
- [x] `Base.metadata.create_all` still bootstraps a fresh DB cleanly
- [x] `school.db` (empty) regenerates without error
- [x] Tests: `tests/test_schema.py` updated for the new shape

## Comments

**Built (commit `cee2b46`):** rewrote `app/models.py` for the derived model — dropped
`Charge`, `Adjustment`, `GenerationRecord`, `FeeItem`, `PaymentAllocation` (and the
`fee_items` relationship on `Class`, `allocations` on `Payment`, `AdjustmentKinds`,
the `JSON` column on charges); added `FeeTemplate` (name, amount_cents),
`Waiver` (student_id, month, year, amount_cents, label, created_by, created_at, unique
(student_id, month, year)), `ClosedMonth` (month, year, unique), `Student.enrolled_on`
(Date, default today) and `Student.archived_on` (Date, nullable), and the `Payment`
month+year tag. `Credit` and all non-billing tables unchanged.

**Verification:**
- `app.models` imports; `Base.metadata.create_all` builds all 13 domain tables on a
  fresh in-memory DB and on the file DB; the 5 removed tables are absent.
- `school.db` (0-byte placeholder) regenerates cleanly; restored to placeholder after
  verification so the commit stays clean.
- `tests/test_schema.py` rewritten for the new shape — 9 tests (tables present/absent,
  cents via `FeeTemplate`, `enrolled_on` default + nullable `archived_on`, `Payment`
  month/year required + stored, waiver unique per student/month/year + stacking on
  other months, closed-month uniqueness, user/class round-trip). Run standalone (green):
  `pytest` against a temp dir with a minimal conftest, because the suite's own
  `tests/conftest.py` imports `app.main`, which still imports removed models.
- **Full suite / typecheck deliberately red at this commit**: `app.fees`, `app.classes`,
  `app.payments`, `app.arrears`, `app.reports` (services + routes) and `app.main` still
  reference the removed models — `pytest` fails at collection (`ImportError: FeeItem`),
  mypy reports 17 errors in 8 files. The app does not start until tickets 02–09 rebuild
  those features on the new schema (expected per the rework plan).
