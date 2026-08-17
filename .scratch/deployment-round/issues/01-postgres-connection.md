# 01 — Postgres connection details

**Type:** research
**Status:** resolved
**Blocked by:**

## Question

What exactly should a school's `DATABASE_URL` be for its Supabase project, and what SQLAlchemy engine/driver/pool settings make a stable cloud connection?

- Driver: psycopg3 (`psycopg[binary]`) vs psycopg2 with SQLAlchemy 2.0.51 — which, and which URL dialect (`postgresql+psycopg://` vs `postgresql+psycopg2://`)?
- Supabase connection string shape: host/port, URL-encoding the password, `sslmode`, transaction-pooler vs direct connection for a long-lived FastAPI process.
- Pool sizing: `pool_size`/`max_overflow`/`pool_pre_ping` tuned under Supabase free-tier connection limits for one school's container.
- Does the existing `make_engine()` (app/db.py) accept the URL unchanged, or does the non-SQLite branch need SSL/pool kwargs?
- Gotchas: IPv6-only Supabase hosts (IPv4 add-on), connection timeouts, keepalives.

Resolve with a `/research` subagent; findings land on a throwaway `research/` branch, and a context pointer is appended from this ticket. The answer feeds 02 (schema portability run).

## Answer

- **DATABASE_URL shape:** `postgresql+psycopg://postgres.<project-ref>:<pct-encoded-password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require` (session pooler, port 5432, IPv4-reachable).
- **Dependency:** `psycopg[binary]==3.3.3`. Existing `make_engine()` non-SQLite branch accepts the URL unchanged; no engine kwargs change needed beyond optional `pool_pre_ping=True`.
- **Gotchas:** ① free-tier direct host `db.<ref>.supabase.co` is IPv6-only — use the pooler or buy the IPv4 add-on; ② percent-encode the DB password in the URL; ③ always `sslmode=require` (`prefer` falls back to plaintext).
- Findings: `research/postgres-connection.md`.
