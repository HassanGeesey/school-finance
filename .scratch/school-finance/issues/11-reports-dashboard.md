# 11 — Reports & dashboard

**What to build:** The reporting surface. A Dashboard with at-a-glance charts (collections, arrears, expenses). Reports: Income vs Expense for a month, Expense by category, Paid students for a specific month (and by extension unpaid), Summarized finance report, and student lists (per class or all classes). Every report has an Export CSV button. Charts render with Chart.js.

**UI:** Build on the design system from **05b** — one reusable report template (filter bar, summary line, table, Export CSV) used by every report; Dashboard = KPI stat cards, charts, recent activity, quick actions.

**Blocked by:** 08 — Payments & receipts, 09 — Expenses, 10 — Arrears, 05b — UI design system & app shell

**Status:** implemented

- [x] Dashboard shows current-month collections, outstanding arrears, expenses, recent payments with charts
- [x] Income vs Expense report for any selected month
- [x] Expense report by category
- [x] Paid students (and unpaid) for a selected month
- [x] Summarized finance report (totals across income, expenses, arrears)
- [x] Student list export for a class or all classes
- [x] Every report has working CSV export

## Comments

Built via TDD on the service seam (`app/reports/service.py`), mirroring tickets 06-10.

- `app/reports/service.py`: `ReportService(db, arrears)` is the single testing seam. `income_vs_expense(month, year)` sums payments and expenses dated inside the month (net = income - expenses) and breaks both down by method. `expense_by_category(month?, year?)` groups by category, largest first, with archived categories keeping their rows. `paid_students(month, year, class_id?)` lists every student billed for the month (never-billed excluded, archived kept): live net charge (base + extras - waivers via `net_cents`), payments cleared to that month's charges (`PaymentAllocation` sums), paid/partial/unpaid status, and charged/collected/outstanding totals. `finance_summary(month, year)` rolls up the month's income/expenses/net plus live arrears (from `ArrearsService`) and credit balances. `student_list(class_id?)` is the register with each class's current monthly fee. `dashboard()` feeds the KPIs, a six-month income/expense series (SQL-windowed to the last 6 months), arrears debt-age band counts, and the all-time expense-by-category lines. `list_periods()` feeds the month dropdowns and includes *charged* months so a billed-but-collected-nothing month is selectable — exactly the paid-students use case. All amounts are integer cents; `ClassNotFound` is raised for unknown classes.
- `app/reports/routes.py`: thin adapters — the hub, the five pages, five CSV exports, and `dashboard_context()` for the root route. Period parsing (`period=YYYY-MM` or month/year) validates the month (400 instead of a 500) and unknown classes become 404s. CSV exports carry a UTF-8 BOM (Excel-friendly), a per-report `Content-Disposition` filename, and a formula-injection guard (`=`, `+`, `@` prefixed). Every report renders through the shared frame.
- `app/templates/reports/`: `_frame.html` is the reusable report template (title + subtitle, Export CSV, then per-report filter/summary/table blocks) from 05b's design system; `_filters.html` holds the shared month/class filter macros (killing the per-page duplication); `index.html` is the reports hub. Pages: `income_expense`, `expense_category` (with All time option; card title includes the selected month label), `paid_students` (month + class filters, status badges), `summary` (a "Month totals" card for the month-scoped figures and a separate "Live balances" card for arrears/credits so the two are never mixed), `students`.
- Dashboard: `app/templates/home.html` rewritten — KPI stat cards (collected, expenses, arrears, active students), Chart.js charts (six-month income/expense bar, arrears-by-age doughnut, expense-by-category bar) fed from `dashboard_context`, recent payments/expenses, and quick actions; `base.html` got a real **Reports** nav item. `app/main.py` wires `ReportService` with `ArrearsService` as `app.state.reports` and uses `dashboard_context` for `/`.
- Tests: `tests/test_reports_service.py` (service rules incl. period filtering, method breakdowns, waivers/extras, archived students, period label, and the new `list_periods`) and `tests/test_reports_routes.py` (page + CSV smoke tests, login gating, Finance officer access, filter-form `period=` submissions, invalid-month 400s, unknown-class 404s, CSV BOM/filename). Full suite green (452 tests); mypy clean (37 files).
- Code review (standards + spec axes) drove a cleanup pass: raw SQL moved out of the routes into `ReportService.list_periods()`; duplicated class-lookup/sort-key helpers extracted; `_by_method` iterates `PAYMENT_METHOD_LABELS`; the `ExpenseCategoryReport` gained a real `period_label` (fixing a silent Undefined → trailing comma in the month-filtered title); the summary page stopped mixing live balances into "Month totals"; the dashboard's six-month series no longer loads every payment/expense ever.
- Design notes: a fully-waived student (net $0, nothing paid) reads as **Paid** — nothing is left to collect, which reads truer than flagging a scholarship kid as unpaid; paid-students' outstanding = charged − collected (allocation basis), matching the arrears definition (credits are reflected once allocated to a charge).
- Verified manually in-browser (chrome-devtools): dashboard KPIs and all three charts with correct data, reports hub, all five pages, all five CSV exports (BOM present in raw bytes, correct filenames), the fixed month-filtered card title, and the refactored filter forms.

Commit: `5dcd349`
