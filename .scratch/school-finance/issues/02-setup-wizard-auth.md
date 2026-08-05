# 02 — Setup wizard + auth

**What to build:** On a fresh database the app shows a setup wizard to create the first Admin account (name, username, password). After that, the office logs in and out. Every other page is behind login, and permissions split by role: Admin can do everything; Finance officer can do daily finance work but not configuration. The app shell shows the user's name and role.

**Blocked by:** 01 — App foundation

**Status:** ready-for-agent

- [ ] Fresh install (no users) shows the setup wizard, not the login form
- [ ] Setup wizard creates the first Admin; the app then requires login
- [ ] Login/out works; passwords stored hashed (PBKDF2), never plaintext
- [ ] All pages except login/setup require a session
- [ ] Role enforcement exists: Finance officer is blocked from configuration/admin-only pages
- [ ] App shell displays logged-in user name and role
