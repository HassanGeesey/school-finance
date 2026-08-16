# 05 — Campus-scoped reports & campus dashboard

**What to build:** Scope the reporting surface to the acting user's Campus: the existing reports (income vs expense, arrears, expense by category, paid students, summarized finance, student register, all CSV exports) and the existing campus dashboard (KPI cards, charts, recent activity) reflect only the acting Campus's data. Campus staff see only their branch's figures; a School with two Campuses gets two independent sets of reports. Period dropdowns and paid/unpaid filters draw from the acting Campus's records only.

**Blocked by:** 04 — Per-campus fee policy and money flows.

**Status:** implemented

- [x] Every report and CSV export reflects only the acting Campus's data
- [x] The campus dashboard's KPIs, charts, and recent activity show only the acting Campus
- [x] Report month dropdowns and paid-status filters draw only from the acting Campus's records
- [x] Cross-Campus figures never leak into a Campus-bound user's output
- [x] Single-school behavior is identical to today
- [x] Tests: seeded-scope service tests + role-authenticated route tests with two Campuses

## Comments

**Built (commit `0c93a93`):**

Scoped `app/reports/service.py` and `app/arrears/service.py` to the acting Campus via the tenant seam (`..tenants.scope`). Reports: `income_vs_expense`, `expense_by_category`, `paid_students` (+ `_students_owed_month`, `_class_name` refuses a foreign class with `ClassNotFound`), `finance_summary` (`_owed_months_across_scope`, `_credits_total`), `student_list`, `billed_periods`/`list_periods` (month dropdowns), and the dashboard aggregations `_payment_amounts_by_month`, `_expense_amounts_by_month`, `_active_student_count`, `_recent_payments`, `_recent_expenses`, `_closed_months`. Arrears: `_closed_months` and the `arrears_report` students query. Legacy NULL-campus rows stay visible to every scope; a School-bound Superadmin sees all Campuses; single-school behavior is unchanged.

**Tests:** `tests/test_reports_scope.py` (10 seeded-scope service tests — income vs expense, expense-by-category, paid students, foreign-class 404, finance summary incl. arrears, student list, period dropdowns, dashboard KPIs/charts/activity, arrears report, legacy NULL rows) and `tests/test_reports_scope_routes.py` (16 role-authenticated route tests with two Campuses — dashboard, arrears, all five reports + their CSV exports, foreign-class 404s, and per-Campus class-filter dropdowns).

**Verification:** full suite `python -m pytest tests -q` green (743 collected, 0 failures); `mypy app` clean (54 files). The working tree also carried unrelated in-flight work for tickets 06–07 (audit scoping + per-Campus branding); those files were left untouched and out of this commit.

