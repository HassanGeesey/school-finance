# 04 — Per-campus fee policy and money flows

**What to build:** Scope the fee and money-flow features to the Campus that owns the underlying student/class, following the pattern ticket 03 establishes. Fee templates, closed months, and expense categories are per-Campus (MD-3): a two-campus school duplicates its identical templates per Campus — copying on creation. Waivers and student amount changes attach only to students of the acting Campus. Payments and credits record only against the acting Campus's students, and expenses record only under the acting Campus's categories. Cross-campus ids are refused or return empty, never data.

**Blocked by:** 03 — Tenant scope plumbing + campus-scoped classes & students.

**Status:** implemented

- [x] Fee templates are per-Campus: each Campus sees only its own templates; a template created in one Campus is invisible in another; a two-campus school duplicates "Standard — $100" per Campus
- [x] Closed months and expense categories are per-Campus, so each branch sets its own fee policy and holidays
- [x] Waivers and amount changes only ever target students of the acting Campus; a cross-campus target is refused
- [x] Payments and credits record only against the acting Campus's students; a cross-campus payment is refused
- [x] Expenses record only against the acting Campus's categories and data
- [x] Single-school behavior is identical to today
- [x] Tests: seeded-scope service tests + role-authenticated route tests with two Campuses

## Comments

**Built (commit `87e54fe`):** ticket 03's pattern applied to every money flow.
`app/fees/service.py` — `TemplateService`: `list_templates`/`list_active_templates`
filter by `scoped_campus_filter`, `get/update/archive/restore` refuse foreign
templates via `in_scope` (404), `create` stamps `campus_for_write(scope())`,
template-amount propagation touches only linked students of the acting Campus
(a corrupt cross-Campus link cannot leak changes), and `linked_student_counts`
counts only the acting Campus's links. `WaiverService.add_waiver` refuses a
foreign student and stamps the acting Campus. `ClosedMonthService` is
per-Campus: uniqueness is per `(campus_id, month, year)` (MD-3), add stamps,
remove refuses another Campus's month, and list/set are scoped. `app/models.py`
— `ClosedMonth` uniqueness is now `(campus_id, month, year)` and
`ExpenseCategory.name` uniqueness is per `(campus_id, name)`, both keeping
legacy NULL-campus rows working (SQLite treats NULLs as distinct). `app/payments/
service.py` — `_get_student`, `_month_paid`, `_closed_months`, `get_payment`,
and `list_recent_payments` are scoped; `record_payment` refuses foreign
students (404) and stamps payment + credit rows. `app/expenses/service.py` —
category lookups/name-uniqueness/list, expense listing/periods, and stamps on
`ExpenseCategory`/`Expense`; a foreign category is refused for record, rename,
and remove.

**Verification:**
- New service tests: `tests/test_fee_money_scope.py` (26 tests) — seeded two-campus
  coverage of templates, closed months, categories, waivers, payments/credits,
  expenses, plus legacy NULL-campus visibility and per-campus closed-month
  account views.
- New route tests: `tests/test_fee_money_routes.py` (6 tests) — role-authenticated
  two-campus flows over the real routes (login as each Campus admin).
- `tests/test_schema.py` updated for the per-Campus unique constraints.
- Full suite: 696 passed. `mypy` clean on all 54 source files.
