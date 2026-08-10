# 03 — Enrollment & effective-dated amounts

**What to build:** Enrollment carries the billing start, and a student's monthly amount is effective-dated. When adding a student (manual or CSV import), the clerk records `enrolled_on` (default today, back-datable) and picks a linked template or a custom monthly amount. Archiving captures `archived_on` (the leaving month's charge stays — service-through-period-end, FW-14). A per-student amount change carries an effective month (default next month); a month's expected uses the amount in force for that month (FW-20). Template raises (ticket 02) add an amount-change entry to each linked student's schedule.

**UI:** Extend the add/import student form with enrolled-on + template/custom-amount fields; the class default template pre-fills. Student edit gains "change monthly amount (effective from month)". Archive dialog records the date.

**Blocked by:** 01 — Schema reshape, 02 — Fee templates & class defaults

**Status:** ready-for-agent

- [ ] `enrolled_on` on add and CSV import (default today, editable)
- [ ] `archived_on` captured when archiving; leaving month still owed
- [ ] Student linked to a template or holds a custom amount
- [ ] Amount-in-force resolution per month (effective-dated changes)
- [ ] Amount changes audited
- [ ] Tests: `tests/test_students_service.py`, `tests/test_students_routes.py`, fee amount resolution tests

## Comments
