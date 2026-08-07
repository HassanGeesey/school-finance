# 0001 — Logo and uploads live in the data directory, not static assets

The app is packaged as a single hidden `.exe` (PyInstaller) that bundles `app/static/` into the binary and must work fully offline. An Admin-uploaded logo therefore cannot be written into `static/` — it would vanish on every repackage and is not a writable location at runtime. The uploaded logo is stored as a file next to the app data (`data/logo.<ext>`, the same writable folder as the SQLite DB and backups), and the database row in `school_profile` stores only the filename.

This keeps all user-created artifacts (database, backups, logo) in one backup-able folder and keeps the bundled static assets immutable.
