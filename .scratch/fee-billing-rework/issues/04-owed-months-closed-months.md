# 04 — Owed months & closed months

**What to build:** The derived month range that everything compares against. For a student, owed months run from the `enrolled_on` month through the `archived_on` month (inclusive), skipping **closed months**, while the student is active (FW-14). **Closed months** are a school-wide list (month + year, unique) maintained by the Admin; a closed month is excluded from every student's owed months, carries no expected amount, and never appears as unpaid (FW-17). This derivation is the single seam used by the account view, payments, and reports.

**UI:** A small "Closed months" manager (e.g. under Settings or the Fees/Templates page): add/remove a closed month. The student account and paid/unpaid views simply never show closed months.

**Blocked by:** 01 — Schema reshape, 03 — Enrollment & effective-dated amounts

**Status:** ready-for-agent

- [ ] Owed-month derivation (enrolled → archived, active only, closed months excluded)
- [ ] Archived students: owed months stop at the archive month
- [ ] Closed months: add/remove, unique per month+year
- [ ] Closed months audited
- [ ] Tests: owed-range derivation + closed-month exclusion (service-level)

## Comments
