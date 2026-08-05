# 13 — Packaging (.exe)

**What to build:** Ship the whole app as one hidden Windows .exe. Double-clicking launches the server with no console window, opens the default browser at localhost automatically, and shows a system-tray icon (Open app / Quit). Only one instance can run — a second launch focuses the first instead of starting a second server. Data and backups live next to the app so the school can back up by copying the folder.

**Blocked by:** 11 — Reports & dashboard, 12 — System admin

**Status:** ready-for-agent

- [ ] A single .exe builds via PyInstaller with no console window
- [ ] Launching the .exe starts the server and opens the default browser automatically
- [ ] System-tray icon offers Open app and Quit; Quit stops the server cleanly
- [ ] Second launch while running does not start a second server
- [ ] The app runs with bundled offline assets
- [ ] Database + backups are stored in a user-visible folder next to the app
