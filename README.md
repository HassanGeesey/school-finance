# School Finance

A self-contained web app for running a school's finances — fee templates,
monthly expected-vs-paid billing, waivers, and a full audit trail. Built
with **FastAPI**, **SQLAlchemy**, and a **Jinja2 + htmx + daisyUI** interface.

> A single-page billing workflow: set up fee templates and class defaults,
> and billing is derived from enrollment — every month a student is expected
> to pay their template amount, payments are recorded against a month, and
> the books compare expected vs paid (with waivers and credit) in the audit
> log.

## Features

**Implemented**

- **Fee templates** — named monthly amounts a class defaults to and a student
  can be linked to (or overridden with a custom amount). Billing is **derived
  from enrollment**: a student is expected to pay their amount in force for
  each owed month (from enrollment through departure, excluding closed
  months), so there are no charge rows and no generation step.
- **Students** — add and search students, import them from CSV, and
  archive/restore without losing history.
- **Payments & waivers** — record a payment against a student + month;
  partial payments clear the oldest unpaid months first and overpayment
  becomes credit. Admin-only waivers reduce a month's expected amount and
  are audited.
- **Expenses** — an Admin-managed category list (add/rename/remove, archived
  rather than deleted) and a record card open to the Finance role: date,
  category, description, amount, and cash/bank/other method, with category and
  month filtering. Every expense and category change is audited.
- **System admin** — an Admin-only settings page. Admins create staff accounts
  (Admin or Finance officer), reset passwords, and disable accounts without
  deleting history (self-disable and last-Admin lockout are refused). The
  SQLite database is backed up automatically on startup and on demand
  ("Backup now") into `data/backups/`, keeping the newest ~30 copies with
  rotation. Admins can shut the app down from the UI (with confirmation); the
  request is audited before the server stops. Every one of these actions lands
  in the audit log.
- **Audit log** — every meaningful action (setup, login, class/student edits,
  fee templates, waivers, amount changes, closed months, payments, user
  management, backups, shutdown) is recorded with who did it, when, and a
  human-readable summary.
- **Roles** — Admin and Finance officer. Finance can view classes, students,
  accounts, and reports, record payments/expenses, and apply waivers; only
  Admin can mutate structure, manage users, run backups, or shut the app down.
- **Design-system shell** — dashboard, grouped sidebar, toasts, confirm
  dialogs, and modal-based editing built on htmx partials.

**Planned (roadmap)**

- Payments & receipts, arrears tracking, reports/dashboard, and packaged EXE
  delivery.

## Tech stack

| Layer        | Choice                                        |
|--------------|-----------------------------------------------|
| Framework    | [FastAPI](https://fastapi.tiangolo.com/)      |
| ORM          | [SQLAlchemy 2.0](https://www.sqlalchemy.org/) |
| Database     | SQLite (single `data/` file, no setup)        |
| Templates    | [Jinja2](https://jinja.palletsprojects.com/)  |
| Interactivity| [htmx](https://htmx.org/) partials, no SPA     |
| Styling      | daisyUI / Tailwind design system (compiled CSS) |
| Server       | [uvicorn](https://www.uvicorn.org/)           |
| Tests        | pytest + httpx (route-level)                  |
| Typing       | mypy (strict, on `app/`)                      |

## Getting started

Requires **Python 3.11+**.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
uvicorn "app.main:create_app" --factory --reload
```

Open <http://127.0.0.1:8000>. On first run you'll be taken through the
**setup wizard**, which creates the Admin account. The SQLite database is
created automatically at `data/school_finance.db`.

> Tip: set `SCHOOL_FINANCE_DATA` to a directory of your choice to store data
> elsewhere, e.g. `SCHOOL_FINANCE_DATA=D:\school_data uvicorn "app.main:create_app" --factory`.

## Project structure

```
app/
  main.py            # Application factory, wiring, middleware
  config.py          # Centralised settings (paths, session, password work factor)
  models.py          # SQLAlchemy domain model
  db.py              # Engine/session helpers
  money.py           # Integer-cent money helpers & formatting
  audit/             # Audit log (actions + service)
  auth/              # Login, sessions, role-based dependencies
  classes/           # Classes & default fee-template picker
  students/          # Students, CSV import, archiving
  fees/              # Fee templates, waivers, closed months + derived account
  admin/             # User management (service + routes)
  system/            # Backups + in-app shutdown (service + routes)
  templates/         # Jinja2 templates & shared UI components
  static/            # Compiled CSS, htmx, JS helpers
tests/               # Service-level (single seam) + route-level tests
```

## Development

```bash
# Run the full test suite
pytest

# Type-check the application
mypy app
```

The test suite covers ~520 cases across the service layer (the single testing
seam — business rules live in the service modules, routes stay thin) and the
routes end-to-end, including role gating, duplicate-safety, audit content, and
the HTMX partials.

## Security notes

- Passwords are hashed with **PBKDF2-HMAC-SHA256** using an OWASP-recommended
  work factor (configurable via `SCHOOL_FINANCE_PBKDF2_ITERATIONS`).
- Sessions are server-side, cookie-backed, with an expiry (`SESSION_TTL_DAYS`).
- Sensitive mutations are Admin-only and every one of them is written to the
  audit log.
