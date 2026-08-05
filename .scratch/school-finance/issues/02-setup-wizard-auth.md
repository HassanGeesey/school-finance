# 02 — Setup wizard + auth

**What to build:** On a fresh database the app shows a setup wizard to create the first Admin account (name, username, password). After that, the office logs in and out. Every other page is behind login, and permissions split by role: Admin can do everything; Finance officer can do daily finance work but not configuration. The app shell shows the user's name and role.

**Blocked by:** 01 — App foundation

**Status:** implemented

- [x] Fresh install (no users) shows the setup wizard, not the login form
- [x] Setup wizard creates the first Admin; the app then requires login
- [x] Login/out works; passwords stored hashed (PBKDF2), never plaintext
- [x] All pages except login/setup require a session
- [x] Role enforcement exists: Finance officer is blocked from configuration/admin-only pages
- [x] App shell displays logged-in user name and role

## Comments

Implemented on 2026-08-05 (commit `f5d3b73`). PBKDF2-HMAC-SHA256 password
hashing with per-user salt (`app/auth/service.py:hash_password`), server-side
sessions resolved by a middleware into `request.state.user`, and two gates in
`app/auth/deps.py` — `require_login` (303 → /login) and `require_admin` (403).
Setup wizard and login templates under `app/templates/auth/`; the app shell
shows the user's name and role badge in `app/templates/base.html`. Verified by
`pytest tests/test_auth_routes.py tests/test_auth_service.py tests/test_app.py tests/test_schema.py` — 34 passed.
