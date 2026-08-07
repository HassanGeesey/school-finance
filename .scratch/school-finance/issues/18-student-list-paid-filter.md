# 18 — Paid/unpaid filter for a month on the student list

**What to build:** The `/students` page gains a Month dropdown (billed months only, defaulting to the most recent billed month) and a Status dropdown (All / Paid / Partial / Unpaid). A new "Paid" column shows each student's paid-status badge and the remaining amount for the selected month (e.g. "Unpaid — $45.00"). Students not billed in the selected month show a dash and are excluded from Paid/Partial/Unpaid results (but appear under All). Paid status is computed per month from charges vs. payments — the same engine the paid-students report uses, no duplicated money logic. All filters (class, name, month, status) combine. When no month has been billed yet, the status filter and Paid column are hidden and the page just lists everyone.

**Blocked by:** 17 — Class filter on the student list

**Status:** implemented

- [x] Month dropdown of billed months (default: most recent billed) + Status dropdown (All/Paid/Partial/Unpaid) on the `/students` page
- [x] Paid column: badge + remaining amount for the selected month; dash for never-billed students
- [x] Paid/Partial/Unpaid filters exclude never-billed students; All shows everyone
- [x] Filters combine (class + name + month + status) and survive reloads (GET form)
- [x] No billed months → status filter + Paid column hidden
- [x] Service/route tests: status per month is correct, never-billed exclusion, combined filters, empty-billing state

## Comments

**What was built:**
- `app/reports/service.py`: `billed_periods()` + `_classify_status()` returning a `StudentStatusRow` (paid cents, billed cents, status, remaining) per student/month, computed from charges vs. payments — the same money engine the paid-students report uses (no duplicated logic).
- `app/students/routes.py`: `/students` gains `period` (YYYY-MM) and `status` GET params with `PAID_STATUS_TONES`; filters combine with class + name.
- `app/templates/students/search.html`: month + status dropdowns (GET form, survives reloads), new "Paid" column with badge + remaining amount (`period_label` from fees service); when no month is billed the status filter and Paid column are hidden.

**Verification:** `tests/test_reports_service.py` (per-month status, never-billed exclusion) + `tests/test_students_routes.py` (combined filters, empty-billing state). Full suite 576 passed; `mypy app` clean.


**Commit:** e37229e (implementation); ticket mark included in same commit
