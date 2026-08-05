# 12 — System admin

**What to build:** The operational safety net. Admin manages users (create/disable staff accounts, reset passwords). Backups: the app copies the SQLite file to a `backups/` folder automatically on startup and via a manual "Backup now" button, keeping ~30 copies and rotating. Admin can shut the app down from within the UI. All actions are audited.

**Blocked by:** 02 — Setup wizard + auth

**Status:** ready-for-agent

- [ ] Admin can create/disable users and reset passwords; Finance cannot
- [ ] Backup runs automatically on startup into `backups/`
- [ ] "Backup now" button creates a backup on demand
- [ ] At most ~30 backups are kept (oldest removed)
- [ ] Admin can shut the app down from the UI with confirmation
- [ ] All admin actions are audited
