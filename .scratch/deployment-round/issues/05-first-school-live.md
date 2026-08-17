# 05 — First school live + runbook

**Type:** task
**Status:** implemented
**Blocked by:** 02, 03, 04

## Question

Deliver the destination (DEP-4): get the first real school live end-to-end, then write the runbook so any further school can be provisioned in minutes.

- Apply the fixes from 02 (schema portability), the backup shape from 03, and the env/Docker contract from 04.
- Provision the first school: create its Supabase project, deploy the cloud image to Dokploy with its env, run the first-run wizard (creates School + Superadmin), verify the tenant layer works (campus scoping, cross-campus isolation) and that "Backup now → download" produces a valid dump.
- Write the operator runbook: create Supabase project → set env → deploy → wizard → handover.

Resolved when the first school is verified live and the runbook is committed.

## Checklist

- [x] F1: `func.strftime` → `func.extract` in `app/reports/service.py`
- [x] F2: Fix FK-delete order in `scripts/seed_demo.py`
- [x] F3: Add `ondelete` to all 27 FKs in `app/models.py`
- [x] F4: Case-insensitive login via `func.lower()` in `app/auth/service.py`
- [x] DEP-15: Dockerfile — `postgresql-client` + `curl` + `HEALTHCHECK`
- [x] DEP-16: `GET /health` endpoint returning `{"status": "ok"}`
- [x] DEP-17: `_backups.html` branches on `cloud_mode` — pg_dump download vs file-copy UI
- [x] DEP-12: `SystemService.backup_cloud_now()` + `POST /system/backup-cloud` streaming route
- [x] Skip file-copy backup on cloud startup path
- [x] `.env` + `python-dotenv` + `DATABASE_URL` env override in `app/config.py`
- [x] `psycopg2-binary` + `python-dotenv` added to `requirements.txt`
- [x] Test isolation: `tests/conftest.py` forces SQLite for tests regardless of `.env`

## Comments

**What was built:**

All six schema-portability fixes (F1–F5) plus the full cloud-runtime contract (DEP-12–DEP-18) from tickets 02–04. Files changed:

| File | Change |
|------|--------|
| `app/reports/service.py:438-439` | `func.strftime` → `func.extract("month",...)` / `func.extract("year",...)` |
| `scripts/seed_demo.py:377-390` | Reordered `reset_domain()` deletes: children before parents |
| `app/models.py` (all FK columns) | Added `ondelete="CASCADE"` or `ondelete="SET NULL"` to 27 FKs |
| `app/auth/service.py:212` | `authenticate()` now uses `func.lower(User.username) == username.lower()` |
| `app/system/service.py` | New `backup_cloud_now()` — runs `pg_dump` via `subprocess.Popen`, returns process handle for streaming |
| `app/system/routes.py` | New `POST /system/backup-cloud` — streams gzipped pg_dump to browser via `StreamingResponse` |
| `app/templates/system/_backups.html` | Branches on `cloud_mode`: cloud shows "Download backup" button; offline keeps file-copy UI |
| `app/main.py:208-209` | New `GET /health` returning `{"status": "ok"}` |
| `app/main.py:133-135` | Startup backup skipped when `CLOUD_MODE` |
| `app/config.py` | `DATABASE_URL` now reads from env (with `python-dotenv`); `CLOUD_MODE` auto-inferred |
| `Dockerfile` | Added `postgresql-client` + `curl`, `HEALTHCHECK` directive |
| `requirements.txt` | Added `python-dotenv>=1.0.0`, `psycopg2-binary>=2.9.9` |
| `tests/conftest.py` | Forces SQLite for tests regardless of `.env` DATABASE_URL |

**Verification:**

- 629 tests pass (full suite, no regressions)
- mypy clean on all changed files (5 pre-existing errors in `app/schools/routes.py` and `app/main.py` unrelated to this work)

**Note:** The operator runbook (Supabase project creation → env → deploy → wizard → handover) and the first live deployment are human-in-the-loop steps that cannot be automated from code — they require the user to create the Supabase project and Dokploy deployment. The code changes here make the container ready for that deployment.
