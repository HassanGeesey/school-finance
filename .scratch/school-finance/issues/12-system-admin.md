# 12 — System admin

**What to build:** The operational safety net. Admin manages users (create/disable staff accounts, reset passwords). Backups: the app copies the SQLite file to a `backups/` folder automatically on startup and via a manual "Backup now" button, keeping ~30 copies and rotating. Admin can shut the app down from within the UI. All actions are audited.

**UI:** Build on the design system from **05b** — settings pages use shared components; shutdown and disable-user actions use the confirm dialog.

**Blocked by:** 02 — Setup wizard + auth, 05b — UI design system & app shell

**Status:** implemented

- [x] Admin can create/disable users and reset passwords; Finance cannot
- [x] Backup runs automatically on startup into `backups/`
- [x] "Backup now" button creates a backup on demand
- [x] At most ~30 backups are kept (oldest removed)
- [x] Admin can shut the app down from the UI with confirmation
- [x] All admin actions are audited

## Comments

**Built**
- `app/admin/service.py` — `AdminUserService` user lifecycle (create/disable/enable/reset-password) with case-insensitive-unique usernames, self-disable and last-active-admin protection, no-op unaudited enable; `USER_ROLE_LABELS` replaces the old inline `ROLE_LABELS`.
- `app/system/service.py` — `BackupService` (pure file mechanics: copy, lexicographic rotation, newest-first listing) + `SystemService` (audited manual/startup backups, audited shutdown via an injectable stopper; `uvicorn_stop` with a daemon force-exit guard for the packaged EXE).
- Routes: `app/admin/routes.py` (GET `/admin` settings page + user mutations over htmx with toast/alert and plain-redirect fallback) and `app/system/routes.py` (POST `/system/backup`, POST `/system/shutdown`).
- Templates: `templates/admin/index.html`, `templates/admin/_users.html`, `templates/system/_backups.html`, `templates/system/shutdown.html`; old placeholder `templates/admin.html` deleted.
- `app/main.py` wiring: `create_app(..., shutdown_stopper, backup_source, backup_dir)`; lifespan now runs `db.create_all()` then `system.backup_on_startup()` (tables must exist before the startup-backup audit write).
- `app/config.py` — `BACKUP_KEEP` (default 30, via `SCHOOL_FINANCE_BACKUP_KEEP`).
- Audit actions `USER_CREATE`, `USER_DISABLE`, `USER_ENABLE`, `USER_PASSWORD_RESET`, `BACKUP_AUTOMATIC`, `BACKUP_MANUAL`, `SHUTDOWN` added to `app/audit/service.py`.

**Verification**
- `pytest`: 517 tests pass (22 admin-service, 22 system-service, 20 admin-route, 10 system-route new tests).
- `mypy app`: no issues across 43 source files.
- Role gating asserted at the route layer (Finance gets 403); shutdown/backup route tests inject a temp backup source and a recording stopper so the test runner can never be stopped; in-memory test DBs skip the backup service entirely.

**Commit:** TBD
