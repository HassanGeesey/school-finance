# 02 — Schema portability to Postgres

**Type:** task
**Status:** resolved
**Blocked by:** 01

## Question

Will the current schema (`Base.metadata.create_all`, app/db.py) and the full existing suite (629 tests, all SQLite) actually run on a Supabase Postgres DB? What breaks, and what needs fixing?

- Scan `app/models.py` and the services for SQLite-isms: types (JSON/booleans/date storage), defaults/auto-increment, string collation, FKs without `ON DELETE`, SQLite-specific SQL (e.g. `date('now')`, `random()`, `INSERT OR REPLACE`), `StaticPool`/memory assumptions.
- Prove it: run the suite against a Postgres URL (a throwaway Supabase project — HITL checklist if the user must create one) and list concrete failures.
- The answer is the concrete fix list that 05 (first school live) executes.

Resolved when the failure list is complete and any needed code fixes are identified (the fixes themselves land in 05).

## Answer — Concrete Fix List

Code scan complete (no Postgres test run yet — that's ticket 05). Findings grouped by severity.

### Must-fix (breaks on Postgres)

| # | What | Where | Fix |
|---|------|-------|-----|
| F1 | `func.strftime("%m", ...)` / `func.strftime("%Y", ...)` — Postgres has no `strftime` | `app/reports/service.py:438-439` | Replace with `func.extract("month", ...)` / `func.extract("year", ...)` (dialect-portable) |
| F2 | `reset_domain()` deletes tables in wrong order — violates FK constraints | `scripts/seed_demo.py:380-389` | Reorder: Expense → Class → FeeTemplate → ExpenseCategory → Student → ClosedMonth (children before parents) |
| F3 | 27 FKs missing explicit `ondelete` — Postgres defaults to `NO ACTION` and blocks parent deletes | `app/models.py` (all FK columns) | Add `ondelete="SET NULL"` for nullable FKs (most campus_id, user refs), `ondelete="CASCADE"` where appropriate (Credit→Payment), `ondelete="NO ACTION"` explicitly for non-nullable FKs |

### Should-fix (silent wrong behavior)

| # | What | Where | Fix |
|---|------|-------|-----|
| F4 | Login username comparison is case-sensitive on Postgres, case-insensitive on SQLite | `app/auth/service.py:212` | Use `func.lower(User.username) == username.lower()` or `.ilike(username)` |
| F5 | No case-insensitive unique index on `users.username` — Postgres allows `"admin"` and `"Admin"` as separate users | `app/models.py` | Add `CheckConstraint(func.lower(User.username), name="uq_username_ci")` or handle in Alembic migration |

### Should-address (risk / hardening)

| # | What | Where | Fix |
|---|------|-------|-----|
| F6 | All tests hardcoded to SQLite — won't catch Postgres-specific issues | `tests/conftest.py`, `tests/mini_app.py`, multiple test files | Add `SCHOOL_FINANCE_TEST_DATABASE_URL` env var, default to `sqlite://`, allow Postgres override |
| F7 | No Alembic migrations — schema via `create_all()` only | `alembic/` doesn't exist | Initialize Alembic before cloud deployment |
| F8 | `create_all()` on cloud path should use `upgrade head` instead | `app/db.py:45`, `app/main.py:129` | Cloud path: use Alembic; offline path: keep `create_all()` |

### Not issues (clean)

- **Types:** SQLAlchemy maps `Integer`, `Boolean`, `DateTime`, `String` correctly for both dialects
- **Auto-increment:** `mapped_column(Integer, primary_key=True)` auto-increments in both
- **Raw SQL:** No `text()`, `execute()`, or raw SQL in services — all ORM
- **JSON/dict storage:** No JSON columns; all `String`/`Integer`/`Boolean`/`DateTime`
- **Engine config:** `StaticPool` + `check_same_thread` correctly gated behind SQLite check in `app/db.py`
- **String ops:** `.ilike()`, `func.lower()` used correctly throughout services
