# 01 — App foundation

**What to build:** The skeleton of the school finance web app. Running the app starts a FastAPI server that serves a styled landing/home page (Tailwind + HTMX, assets bundled locally, works offline). SQLite + SQLAlchemy are wired up (schema created on startup), config is centralised, and the automated test harness runs against an in-memory SQLite database with a pytest fixture. Nothing user-facing beyond a styled shell yet.

**Blocked by:** None — can start immediately

**Status:** implemented

- [x] App starts and serves a styled home page in the browser at localhost
- [x] Static assets (Tailwind CSS, HTMX, Chart.js) are bundled locally, not fetched from the internet
- [x] Database connects; schema is created automatically on startup
- [x] `pytest` runs green against an in-memory SQLite database
- [x] Money stored as integer cents (no floats) wherever amounts appear

## Comments

Implemented on 2026-08-05. The app factory (`app/main.py:create_app`) serves a
Tailwind-styled home page; assets (Tailwind CSS, HTMX 2.0.4, Chart.js 4.4.7) are
bundled under `app/static/` and built from `assets-src/`. SQLAlchemy schema — all
13 domain tables from the spec — is created on startup against
`data/school_finance.db`. Money helpers (`app/money.py`) store amounts as integer
cents. `pytest` (12 tests) runs green against an in-memory SQLite database
(`tests/conftest.py`). Verified manually in a browser: home page renders, no
console errors, all local assets load with 200.
