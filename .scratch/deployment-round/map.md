# Deployment round — map

**Effort:** Cloud deployment round of the multi-school feature (wayfinder).

## Destination

One school's cloud deployment live: the app running on Dokploy against that school's **own Supabase Postgres**, tenant layer working for real (first-run wizard creates the School + Superadmin; per-campus scoping live), a **manual downloadable backup** from the settings page, and a documented **runbook** for provisioning each further school. RLS and Management-API provisioning stay out.

## Notes

- Domain context: `CONTEXT.md` → "Schools & campuses", "Users & roles". Decisions: `project-decisions.md` → "Deployment round (wayfinder charting)" (DEP-1..8). Multi-school build spec: `.scratch/multi-school/spec.md` (the "one central Postgres" lines are superseded by DEP-1).
- **This effort carries execution** (DEP-4) — tickets do real work, not just decisions.
- Consulting skills: `/research` for external facts, `/grilling` for decisions, `/domain-modeling` for term conflicts.
- Grilling rule: record every question/answer in `project-decisions.md` as we go (AGENTS.md).
- Env facts: `.env` holds `SUPABASE_URL`, publishable/secret keys, `SUPABASE_JWKS_URL` (project `dalskfgtmelcabxmlhlj.supabase.co`). `.env` is untracked; `SUPABASE_SECRET_KEY` is sensitive.

## Decisions so far

- [01 — Postgres connection details](issues/01-postgres-connection.md) — `postgresql+psycopg://` + `psycopg[binary]==3.3.3`; use Supabase session pooler (port 5432, IPv4), `sslmode=require`, password percent-encoded; `make_engine()` needs no change.
- [02 — Schema portability](issues/02-schema-portability.md) — Fix list complete: `func.strftime` → `func.extract` (F1), seed script delete order (F2), 27 FKs missing `ondelete` (F3), login case-sensitivity (F4/F5). Risk items: test DB env var (F6), Alembic (F7/F8). Fixes land in 05.
- [03 — Cloud backup](issues/03-cloud-backup.md) — `pg_dump` only, gzipped, streamed via `Popen` + `StreamingResponse`. Settings page button. Database only. Filename: `school_finance-TIMESTAMP.sql.gz`.
- [04 — Cloud runtime](issues/04-cloud-runtime.md) — Env: `DATABASE_URL` + `DATA=/data` + optional `DISABLE_SHUTDOWN=1`. Dockerfile: `postgresql-client` + healthcheck. New `GET /health`. Hide file backup UI on cloud. No compose changes.

## Not yet specified

- **Management-API provisioning automation** (creating a school's Supabase project programmatically) — out of reach until provisioning is proven manually (DEP-2).
- **Per-school subdomain / branding of the URL** (C-6) — the first school can go live on a plain Dokploy URL.
- **Monitoring / alerting / backups verification at many-school scale** — connection pooling headroom once several schools are live.
- **Per-school billing / storage reporting** (C-6) — no billing surface exists yet.
- **Alembic / schema migrations** — deferred while `create_all` is sufficient (DEP-6).

## Out of scope

- **Postgres RLS** — C-3 follow-up ticket; per-school DBs (DEP-1) make cross-school RLS moot anyway (DEP-7).
- **Management-API provisioning** — operator-provisioned by design (DEP-2); automation is fog, not this effort.
- **Central cross-school views / one-DB-for-all** — superseded by DEP-1.
- **Automated Postgres restore** — restore stays manual (DEP-3).
- **Alembic migrations** — deferred (DEP-6).
- **.exe / offline path changes** — unchanged (UR-15); local SQLite file backups stay as-is.
- **Global superadmin / platform operator** — rejected (UR-13).
