# Postgres connection research (deployment-round #01)

**Status:** resolved (research only — no code changes)
**Feeds:** 02 (schema portability run)

## TL;DR

- Driver: **psycopg3** → `psycopg[binary]`, URL dialect **`postgresql+psycopg://`** (SQLAlchemy 2.0.51 has a first-class psycopg3 dialect; plain `postgresql://` still resolves to psycopg2).
- URL: use the Supabase **session pooler** for the long-lived FastAPI process:
  `postgresql+psycopg://postgres.<ref>:<pct-encoded-password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require`
- Engine: existing `make_engine()` non-SQLite branch (`create_engine(database_url)`) accepts the URL unchanged. Only add pool kwargs + sslmode (via URL param) for stability.
- Pool: `pool_size=5`, `max_overflow=5`, `pool_timeout=30`, `pool_pre_ping=True`.

## 1. Driver + dialect

| Choice | URL dialect | Notes |
|---|---|---|
| psycopg3 (`psycopg[binary]`) | `postgresql+psycopg://` | Current, actively maintained, sync + async support; dedicated SQLAlchemy dialect since 2.0 |
| psycopg2 (`psycopg2-binary`) | `postgresql+psycopg2://` | Legacy; only needed for old code |

- SQLAlchemy docs + dialect source (rel_2_0_51): `postgresql+psycopg://` selects the psycopg 3 dialect and `create_engine()` auto-selects the sync `psycopg.connect()`.
- Latest psycopg on PyPI: **3.3.3** (Feb 18, 2026). Pin `psycopg[binary]` (bundled libpq; no system deps — good for slim images).

## 2. requirements.txt line

```
psycopg[binary]==3.3.3
```

## 3. Connection URL (Supabase)

Recommended for the app (long-lived process, one uvicorn worker per school container):

```
postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

- **User:** `postgres.<project-ref>` (e.g. `postgres.dalskfgtmelcabxmlhlj`).
- **Port 5432** = session pooler; **port 6543** = transaction pooler. Do **not** use the transaction pooler — it assumes short-lived connections and breaks SQLAlchemy's `QueuePool` (session reuse / prepared-statement deallocation issues).
- **Session pooler** is reachable over IPv4; the **direct** host `db.<project-ref>.supabase.co:5432` is **IPv6-only on the free tier** unless you buy the (paid) IPv4 add-on. Docker containers on typical IPv4-only VPS/cloud hosts cannot reach the direct host.
- Alternative (direct, if IPv6/IPv4 add-on available): `db.<project-ref>.supabase.co:5432`.

### Password encoding

Per libpq / RFC 3986, any of `@ : / ? # % [ ]` etc. in the password must be percent-encoded. Example: password `a@b:c` → `a%40b%3Ac`. Failing to encode `@` corrupts the `user:pass@host` parse.

### sslmode

- libpq default is `prefer` (tries SSL, silently falls back to plaintext). Supabase requires/inspects TLS, so set **`sslmode=require`** explicitly in the URL.
- Getting it into the URL (`?sslmode=require`) means **no engine code change** — the dialect passes it through.

## 4. Engine changes (`app/db.py`)

`make_engine()` (app/db.py) routes non-`sqlite` URLs straight to `create_engine(database_url)` — the `postgresql+psycopg://` URL works **unchanged**. Recommended kwargs to add (SQLAlchemy pool docs):

```python
engine = create_engine(
    database_url,
    pool_size=5,
    max_overflow=5,
    pool_timeout=30,
    pool_pre_ping=True,
)
```

Rationale:
- `pool_size=5`, `max_overflow=5` — single worker, one school's load; keeps concurrent connections well under Supabase free-tier limits (≈60 direct / ≈200 pooler) even with `create_all` + a few app sessions.
- `pool_pre_ping=True` — pessimistic disconnect check on checkout (default SQLAlchemy recovers only on next error); Supabase can idle-drop/restart connections, so pre-ping avoids 500s.
- No `poolclass` change needed; `QueuePool` default is correct for a threaded sync app.

## 5. Gotchas

1. **IPv6-only direct host on free tier** — `db.<ref>.supabase.co` has no IPv4 unless you pay for the add-on. Use the session pooler (`aws-0-<region>.pooler.supabase.com:5432`) from Docker/VPS; only the pooler is guaranteed IPv4-reachable.
2. **Password must be percent-encoded** in the URL — `@`, `:`, `/`, `?`, `#`, `%` in a password silently break the URI parse (`@` especially).
3. **`sslmode=prefer` falls back to plaintext** — always set `?sslmode=require` (also keeps Supabase's TLS inspection happy).
4. **Transaction pooler vs session pooler** — SQLAlchemy `QueuePool` assumes one long-lived session per connection; the transaction pooler (port 6543) deallocates/cycles sessions and breaks pooling. Session pooler (5432) only.
5. **psycopg3 prepared statements** — default `prepare_threshold=5`; prepared statements are per-connection and **not shareable across processes** (psycopg/psycopg issue #911). Fine with a single uvicorn worker; if multiprocessing is ever added, disable via `prepare_threshold=None` (connect kwarg).
6. **`connect_timeout`** — libpq default waits indefinitely; set `?connect_timeout=10` so a dead pooler/direct host fails fast instead of hanging a request.

## 6. Sources

- SQLAlchemy 2.0 docs — Connection Pooling (`pool_size`, `max_overflow`, `pool_pre_ping`): https://docs.sqlalchemy.org/en/20/core/pooling.html
- SQLAlchemy 2.0 psycopg dialect source (rel_2_0_51): `lib/sqlalchemy/dialects/postgresql/psycopg.py` (`postgresql+psycopg://` connectstring)
- PostgreSQL libpq docs — Connection URIs / percent-encoding, `sslmode`, `connect_timeout`: https://www.postgresql.org/docs/current/libpq-connect.html
- Supabase docs — connection modes (direct vs pooler, session/transaction), IPv4 add-on: https://supabase.com/docs/guides/database/connecting-to-postgres
- psycopg 3 docs — `Connection.connect()` / `prepare_threshold` (default 5; `None` disables): https://www.psycopg.org/psycopg3/docs/api/connections.html
- psycopg issue #911 (prepared statements across processes): https://github.com/psycopg/psycopg/issues/911
- PyPI — psycopg 3.3.3 (2026-02-18)
