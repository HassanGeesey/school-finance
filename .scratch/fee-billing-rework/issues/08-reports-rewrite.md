# 08 — Reports rewrite (derived from the comparison)

**What to build:** All fee reports derive from the owed-month comparison instead of `Charge` rows. **Paid/unpaid per month** (`ReportService.paid_students`): every student with an owed month in the selected period (closed months excluded), showing expected, paid, credit, remaining, status. **Arrears** (`ArrearsService`): the sum of monthly shortfalls across owed months, age-banded by month. **Student list paid column** (`/students`): per selected month, same derivation. **Income vs expense** and dashboard KPIs stay date-based (unchanged). Month dropdowns now come from owed months + payment months + expense months (no `Charge` periods).

**UI:** No new screens — existing reports re-render from the new service methods; the paid/unpaid report gains the expected/paid/credit columns.

**Blocked by:** 04 — Owed months & closed months, 06 — Month-tagged payments & credit, 07 — Student account view

**Status:** ready-for-agent

- [ ] Paid/unpaid per month derived from owed months (closed months excluded)
- [ ] Arrears = accumulated monthly shortfalls, age-banded
- [ ] `/students` paid column uses the same derivation
- [ ] Month dropdowns use owed/payment/expense months
- [ ] Dashboard + income-vs-expense unchanged and still pass
- [ ] Tests: `tests/test_reports_service.py`, `tests/test_arrears_service.py` reworked (+ routes)

## Comments
