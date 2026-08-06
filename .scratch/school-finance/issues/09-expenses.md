# 09 — Expenses

**What to build:** Recording money out. The Admin manages an expense category list (e.g. Salaries, Utilities, Supplies, Maintenance, Transport, Other). Finance records expenses (date, category, description, amount, method). No attachments. Expense actions are audited.

**UI:** Build on the design system from **05b** — use shared components; expense recording via a form card with toast on save; category management with a modal.

**Blocked by:** 02 — Setup wizard + auth, 05b — UI design system & app shell

**Status:** implemented

- [x] Admin can add/rename/remove expense categories
- [x] Finance can record an expense (date, category, description, amount, method)
- [x] Expense list is viewable (filter by category/month)
- [x] Category list changes and expense records are audited

## Comments

Built with TDD at the established seams: business rules in
`app/expenses/service.py` (`ExpenseService` — `create_category`,
`rename_category`, `remove_category` (archives via `is_active`), `record_expense`,
`list_expenses` with category/month filtering, `list_periods`) and thin route
adapters in `app/expenses/routes.py`. Amounts are integer cents via
`app.money`; categories carry a unique name and soft-delete flag; an `Expense`
rows holds category FK, description, amount_cents, method, occurred_on,
recorded_by. Four new audit actions (category add/rename/remove, expense
record) with human-readable labels. Role gates: `require_login` for viewing and
recording (Finance can record), `require_admin` for category management.

UI follows the 05b design system: record form card with htmx POST (toast via
`HX-Trigger`, plain 303 redirect fallback without htmx), category management in
a `<dialog>` modal. After a category mutation the whole record card + list
re-renders via `expense-categories-changed` (GET `/expenses/dashboard`
partial), so a just-added first category reveals the form instead of a stale
empty-state alert. Verified manually in a browser (add category → dropdown and
form update without reload; record expense → list/total update; audit log
entries appear). Nav item added in `base.html`; README feature list updated.

Verification: `python -m pytest -q` — 367 passed. `python -m mypy app` —
Success: no issues found in 31 source files. Manual smoke on a live server as
above.

Commit: `34a0c31`
