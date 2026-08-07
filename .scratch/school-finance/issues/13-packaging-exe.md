# 13 — Packaging (.exe)

**What to build:** Ship the whole app as one hidden Windows .exe. Double-clicking launches the server with no console window, opens the default browser at localhost automatically, and shows a system-tray icon (Open app / Quit). Only one instance can run — a second launch focuses the first instead of starting a second server. Data and backups live next to the app so the school can back up by copying the folder.

**UI:** No UI work — this ticket packages the design-system app; the bundled offline assets (app.css, Inter font, icons, HTMX, Chart.js) must be included in the .exe.

**Blocked by:** 11 — Reports & dashboard, 12 — System admin, 05b — UI design system & app shell

**Status:** implemented

- [x] A single .exe builds via PyInstaller with no console window
- [x] Launching the .exe starts the server and opens the default browser automatically
- [x] System-tray icon offers Open app and Quit; Quit stops the server cleanly
- [x] Second launch while running does not start a second server
- [x] The app runs with bundled offline assets
- [x] Database + backups are stored in a user-visible folder next to the app

## Comments

Implemented 2026-08-07. Desktop launcher in `app/desktop/launcher.py` (single-instance guard via loopback control socket, uvicorn background thread, pystray tray with Open app / Quit, browser auto-open, `--data-dir`), built by `packaging/SchoolFinance.spec` via `scripts/build-exe.ps1` into a single 30.6 MB `dist/SchoolFinance.exe` (no console, `upx=False`, bundled templates + static offline assets).

Verification (final build, 2026-08-07):
- 590 tests pass, `mypy app` clean on 49 source files.
- Smoke test on the built exe: server responds on 127.0.0.1:8000; offline assets served from the bundle (app.css 106313, chart.umd.min.js 205889, htmx.min.js 50917, Inter woff2 23664 bytes).
- Second launch exits 0 while first instance keeps running (single-instance guard).
- Data persists across launches in `dist/data` (school_finance.db + backups/ next to the exe; re-setup correctly rejected with "An admin account already exists").
- Admin login + POST `/system/shutdown` returns 200 and the whole process exits cleanly.

Commit: TBD (filled in by the follow-up mark commit).
