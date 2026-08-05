# 03 — Audit log

**What to build:** An append-only audit trail: every payment, expense, fee generation, adjustment, and configuration change is logged with who did it, when, and a summary of what changed. The Admin can browse the log (filtered/recent first). No audit entry can be edited or deleted through the app.

**Blocked by:** 02 — Setup wizard + auth

**Status:** implemented

- [x] Audit entries are recorded for every auditable action across the app
- [x] Each entry carries user, timestamp, and a readable summary of the change
- [x] Admin can browse the audit log in the UI; Finance officer cannot
- [x] No UI path edits or deletes audit entries

## Comments

Implemented on 2026-08-05 (commit). Append-only trail via `app/audit/service.py`
(`AuditService.log`) — no update/delete operations exist in the service, and no
route offers one. Each entry stores `user_id`, `action`, `summary`, and a
`created_at` timestamp; setup (attributed to "System"), login, and logout are
the live audited actions so far (`app/auth/service.py`), and later features
(payments, expenses, fee generation, adjustments, configuration) record through
the same service. Admin-only browse at `/audit` (`app/audit/routes.py` +
`app/templates/audit/index.html`): recent-first, filterable by action with
pagination; Finance officer gets 403; a nav link appears in the header for
admins. Verified by `pytest tests/test_audit_service.py tests/test_audit_routes.py` plus the full suite (62 passed), mypy clean.
