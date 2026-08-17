# 04 — Cloud runtime: env contract + Docker

**Type:** grilling
**Status:** resolved
**Blocked by:**

## Question

Which runtime changes turn a container into a "cloud school" (DEP-4/DEP-8)? Decision to lock:

- **Env contract**: `DATABASE_URL` (that school's Supabase Postgres), `SCHOOL_FINANCE_CLOUD`/`SCHOOL_FINANCE_DISABLE_SHUTDOWN`, cookie flags — the exact set a Dokploy deployment must set.
- **Dockerfile**: add `postgresql-client` (for 03), anything else (timezone, non-root, healthcheck).
- **App switches**: disable local file-copy backups + backup-on-startup on the cloud path (no SQLite file), hide the file backup list vs re-point it, secure session cookie behind the HTTPS proxy.
- **compose/Dokploy**: env wiring, no data volume for the DB (it's remote), what stays local (logo uploads per campus).

Resolved by a grilling session with the user; the locked contract is executed in 05.

## Answer — Locked Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| DEP-14 | **Env contract:** `DATABASE_URL` (required) + `SCHOOL_FINANCE_DATA=/data` (Docker) + `SCHOOL_FINANCE_DISABLE_SHUTDOWN=1` (optional) | `SCHOOL_FINANCE_CLOUD` auto-inferred from URL prefix (I-1). Three vars, no more. |
| DEP-15 | **Dockerfile:** `postgresql-client` + `HEALTHCHECK` + `EXPOSE 8000` | Minimal. No timezone (app uses UTC everywhere), no non-root (Dokploy manages). |
| DEP-16 | **New `GET /health`** returning `{"status": "ok"}` | Clean contract for Docker/LB healthcheck. One line of code. |
| DEP-17 | **Hide file backup UI on cloud** | Settings page shows pg_dump download instead. No dead buttons. Offline path untouched. |
| DEP-18 | **No docker-compose.yml changes** | `DATABASE_URL` injected via Dokploy env UI, not in the file. |

## Implementation Notes

### Dockerfile changes
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
# ... existing steps ...
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1
```
(Add `curl` to the apt-get install if not already present, or use a Python-based healthcheck.)

### App changes
- `GET /health` route in `app/main.py` or a new `app/health.py` — returns `{"status": "ok"}`.
- `app/system/service.py`: `SystemService` gains `backup_cloud_now()` — runs `pg_dump` via `Popen`, returns the process handle for streaming.
- `app/system/routes.py`: on `CLOUD_MODE`, the backup route calls `backup_cloud_now()` and returns a `StreamingResponse`.
- `app/templates/system/_backups.html`: branches on `settings.CLOUD_MODE` — cloud renders a "Download backup" button; offline renders the existing file-copy UI.
- `app/main.py` lifespan: startup backup is skipped on cloud (`if not settings.CLOUD_MODE: system.backup_on_startup()`).
- `app/auth/deps.py` or middleware: sets `Secure` flag on session cookie when `request.is_secure` (DEP-11 from D-11).
