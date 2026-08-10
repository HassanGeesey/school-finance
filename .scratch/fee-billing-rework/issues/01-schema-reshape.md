# 01 — Schema reshape for the compare model

**What to build:** Replace the charge-based billing schema with the derived model. In `app/models.py`: drop `Charge`, `Adjustment`, `GenerationRecord`, `FeeItem`, `PaymentAllocation`; add `FeeTemplate` (name, amount_cents), `Waiver` (student_id, month, year, amount_cents, label, created_by, created_at), `ClosedMonth` (month, year, unique), `Student.enrolled_on` (Date, default today) and `Student.archived_on` (Date, nullable), and `Payment.month` / `Payment.year` (Integer, the month tag). `Credit` stays. Unique constraint on `(student_id, month, year)` for waivers. No data migration — the DB is effectively empty (FW-18).

**Blocked by:** —

**Status:** ready-for-agent

- [ ] Old tables removed from the model; new tables/columns added
- [ ] `Base.metadata.create_all` still bootstraps a fresh DB cleanly
- [ ] `school.db` (empty) regenerates without error
- [ ] Tests: `tests/test_schema.py` updated for the new shape

## Comments
