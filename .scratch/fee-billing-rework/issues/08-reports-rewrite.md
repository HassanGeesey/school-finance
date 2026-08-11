# 08 — Reports rewrite (derived from the comparison)

**What to build:** All fee reports derive from the owed-month comparison instead of `Charge` rows. **Paid/unpaid per month** (`ReportService.paid_students`): every student with an owed month in the selected period (closed months excluded), showing expected, paid, credit, remaining, status. **Arrears** (`ArrearsService`): the sum of monthly shortfalls across owed months, age-banded by month. **Student list paid column** (`/students`): per selected month, same derivation. **Income vs expense** and dashboard KPIs stay date-based (unchanged). Month dropdowns now come from owed months + payment months + expense months (no `Charge` periods).

**UI:** No new screens — existing reports re-render from the new service methods; the paid/unpaid report gains the expected/paid/credit columns.

**Blocked by:** 04 — Owed months & closed months, 06 — Month-tagged payments & credit, 07 — Student account view

**Status:** implemented

- [x] Paid/unpaid per month derived from owed months (closed months excluded)
- [x] Arrears = accumulated monthly shortfalls, age-banded
- [x] `/students` paid column uses the same derivation
- [x] Month dropdowns use owed/payment/expense months
- [x] Dashboard + income-vs-expense unchanged and still pass
- [x] Tests: `tests/test_reports_service.py`, `tests/test_arrears_service.py` reworked (+ routes)

## Comments

The derived reports were already landed (checkpoint `cf11560`): `ReportService.paid_students` (service.py:493) filters to owed months via the `student_account` seam with closed months excluded; `ArrearsService.arrears_report` derives `max(expected − paid − credits, 0)` with current/late/overdue age bands (30/60-day thresholds); `list_periods`/`billed_periods` union owed months + payment months + expense months; `student_status_rows` drives the `/students` paid column; dashboard + income-vs-expense are date-based and unchanged. This ticket closes the remaining gaps:

- **Report columns:** the paid/unpaid report now shows the expected/paid/credit columns per the ticket — `app/templates/reports/paid_students.html` renames the "Charged" stat + header to "Expected" and adds a Credit column (`line.credit_cents`, the credit the month consumed via the account credit pass); the CSV export (`app/reports/routes.py` `paid_students_csv`) matches with "Expected"/"Credit" columns. Empty-state colspan bumped to 7.
- **Tests:** `tests/test_reports_service.py` (10) — paid_students expected/paid/credit/remaining/status per student, closed-month exclusion, archived student still owed, paid/partial/unpaid counts, report totals, `list_periods` union of owed/payment/expense months newest-first, `student_status_rows` (owed status, `None` when not owed, status filter), income-vs-expense stays date-based. `tests/test_arrears_service.py` (9) — owed = expected − paid − credit (positive only), exclusion for fully-paid/credit-covered/never-owed, age-band thresholds pinned via `today=`, oldest-debt-first ordering, archived students keep arrears, class/student statuses exposed.
- **Verification:** `pytest tests/test_reports_service.py tests/test_arrears_service.py tests/test_reports_routes.py tests/test_arrears_routes.py` → 54 passed. `mypy app/reports app/arrears` → clean.
- **Note:** an initial test failure surfaced a lazy-load edge (`student.fee_template` detached after session close) reachable only when a template-linked student has no seeded `StudentAmountChange`; real data always seeds one (`students/service.py` `_seed_amount`), so the test helper mirrors the seed rather than changing the service.
- **Commit:** `c58a546`.
