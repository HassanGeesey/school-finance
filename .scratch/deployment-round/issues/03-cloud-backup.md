# 03 — Cloud backup: manual downloadable backup

**Type:** grilling
**Status:** resolved
**Blocked by:**

## Question

What exactly is the "manual downloadable backup" on the cloud path (DEP-3)? Decision to lock:

- Format: `pg_dump` of the Postgres DB streamed to the browser (gzipped SQL) vs an app-level logical export (CSV/JSON per table) vs both.
- Delivery: "Backup now" button on the settings page next to the offline file backups, producing a download; keep the existing automatic startup file-copy for the offline path untouched.
- Runtime: the Docker image gains `postgresql-client` for `pg_dump`; credentials come from the same `DATABASE_URL`.
- Scope: restore stays manual (Supabase dashboard); no automated restore this round.

Resolved by a grilling session with the user; the locked shape is executed in 05.

## Answer — Locked Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| DEP-9 | **`pg_dump` only** (gzipped SQL) | No CSV/JSON export — it loses schema/indexes/FKs. One button, one format, one restore path. |
| DEP-10 | **Settings page** (`GET /admin` backups card) | The admin's config surface. Not the School Dashboard. |
| DEP-11 | **Database only** | Logo files are small and re-uploadable. No tar of uploads. |
| DEP-12 | **`Popen` + `StreamingResponse`** | No temp file, streams directly to browser. `pg_dump` runs via `postgresql-client` in the Docker image. |
| DEP-13 | **`school_finance-YYYYMMDD-HHMMSS.sql.gz`** | Matches existing SQLite backup naming convention. |

## Implementation Notes

- On cloud (`settings.CLOUD_MODE`), the backups card renders a different template: a "Download backup" button that POSTs to `/system/backup-cloud` (or reuses the existing route with a cloud branch).
- The route calls `Popen(["pg_dump", "--dbname={DATABASE_URL}", "--no-owner", "--no-privileges"], stdout=PIPE)`, wraps stdout in a `StreamingResponse` with `Content-Disposition: attachment; filename=school_finance-{timestamp}.sql.gz"`.
- The existing `BackupService` (SQLite file copy) is untouched — it's used only on the offline path.
- `SystemService` gains a `backup_cloud_now()` method that runs pg_dump and streams the output, with audit logging.
