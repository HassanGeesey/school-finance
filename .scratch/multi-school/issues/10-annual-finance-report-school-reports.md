# 10 — Annual Finance Report & School Reports

**What to build:** A per-Campus **Annual Finance Report** — twelve monthly income/expense rows, annual totals, and an annual arrears figure (the derived comparison capped to the year's owed months) — reachable from the campus Reports hub by campus staff, and a **School Reports** hub for Superadmin/Owner: per-Campus Annual Finance Report cards (via the read-only `/campuses/{id}/reports/annual` drill-down) plus an **All Campuses annual rollup** (`/school/reports/annual`) showing every Campus side by side with school totals. All three surfaces get CSV export.

**Blocked by:** 05 — Campus-scoped reports & campus dashboard; 08 — School Dashboard.

**Status:** implemented

- [x] The Annual Finance Report renders 12 monthly income/expense rows + annual totals + annual arrears, scoped to the acting Campus
- [x] The arrears figure caps to the year's owed months (Dec 31 for a completed year, today for the current year)
- [x] Year dropdown lists only years with data; defaults to the newest data year
- [x] Campus staff reach the report from the campus Reports hub; Superadmin/Owner reach it read-only via `/campuses/{id}/reports/annual`
- [x] A **School Reports** rail item + hub (`/school/reports`) lists per-Campus Annual Finance Report cards and the All Campuses rollup
- [x] The rollup shows every Campus side by side (income, expenses, net, arrears) plus school totals and a school-wide monthly cash-flow table
- [x] CSV export on all three surfaces: `/reports/annual.csv`, `/campuses/{id}/reports/annual.csv`, `/school/reports/annual.csv`
- [x] Tests: seeded-scope service tests (per-month figures, arrears cap, year dropdown, rollup isolation/totals) + role-authenticated route tests (staff isolation, Superadmin/Owner hub + rollup read-only, CSVs)

## Comments

Grilling session: `project-decisions.md` → "Annual finance report + School Reports" (Y-1..Y-6). Terms: `CONTEXT.md` → "Reporting" (Annual Finance Report, School Reports).

**Built (commit: NOT COMMITTED — working tree carries unrelated in-flight UI-round edits in the shared template files):**

Service: `app/reports/service.py` gains `annual_finance(year)` (12 `PeriodLine` months + totals + an annual arrears figure via `ArrearsService.arrears_report(today=snapshot_date)`, where `snapshot_date = min(date(year,12,31), today)` so a completed year is capped at Dec 31 and the current year at today), `annual_years()` (distinct years with owed months/payments/expenses), and an `end` bound on the by-month payment/expense helpers. `app/schools/service.py` gains `annual_years()` and `annual_rollup(year)` (runs the report service under each Campus scope, like `_kpi`), returning per-Campus reports, school totals, and a school-wide monthly series.

Routes: campus `GET /reports/annual` + `/reports/annual.csv` and a new card on the campus Reports hub; drill-down dispatch extended with `annual`; new school-bound `GET /school/reports` (hub), `GET /school/reports/annual` + `/school/reports/annual.csv` (rollup). Fixed two latent issues the new drill-down CSV exposed: the `/campuses/{id}/reports/{report_name}.csv` route was registered *after* the generic `{report_name}` route (so every drill-down CSV 404'd — reordered), and the `run_with` dispatch's `handler` variable needed a `Callable[..., Response]` annotation to satisfy mypy (pre-existing ticket-08 errors, plus the new `annual` branch). Also annotated `app/main.py`'s `/` route return as `Response` (pre-existing mypy error).

Templates: `reports/annual.html` (frame + new `year_filter` macro), `school/reports.html` (hub), `school/annual_rollup.html` (rollup), and a `calendar-days` icon. Rail nav: a **Reports** item for Superadmin/Owner under the "School" group; Overview active only on `/school` + drill-down.

**Tests:** `tests/test_reports_annual.py` (13) — seeded-scope service tests (per-month roll-up, campus isolation, school-scope aggregation, arrears capped to the year's owed months, year dropdowns, rollup isolation/totals) and role-authenticated route tests (staff isolation, Superadmin hub + rollup + drill-down + CSVs, Owner read-only, staff 403s).

**Verification:** `python -m pytest tests/test_reports_annual.py -q` green (13 passed). Full suite green except two **pre-existing** failures on the `ui` branch (`test_app.py::test_authenticated_pages_use_the_design_system_shell`, `test_profile_routes.py::test_app_shell_shows_the_school_name_after_setup`) that assert the old pre-UI-round shell/title and fail against the redesigned templates independent of this work. `mypy app` clean (58 files).
