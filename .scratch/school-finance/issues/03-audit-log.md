# 03 — Audit log

**What to build:** An append-only audit trail: every payment, expense, fee generation, adjustment, and configuration change is logged with who did it, when, and a summary of what changed. The Admin can browse the log (filtered/recent first). No audit entry can be edited or deleted through the app.

**Blocked by:** 02 — Setup wizard + auth

**Status:** ready-for-agent

- [ ] Audit entries are recorded for every auditable action across the app
- [ ] Each entry carries user, timestamp, and a readable summary of the change
- [ ] Admin can browse the audit log in the UI; Finance officer cannot
- [ ] No UI path edits or deletes audit entries
