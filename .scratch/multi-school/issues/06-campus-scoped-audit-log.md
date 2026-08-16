# 06 — Campus-scoped audit log

**What to build:** Audit entries carry the scope of the action (US-20/21). Campus-level actions — payments, expenses, students, classes, fee templates, waivers, closed months, branding — are tagged to the Campus they happened in; school-level actions — Campus creation, Campus Admin assignment, Owner management — are tagged School-wide (nullable Campus). The audit browser shows only what the actor may see: a Campus Admin browses their own Campus's entries; the Superadmin browses every entry in their School, including school-level ones.

**Blocked by:** 03 — Tenant scope plumbing + campus-scoped classes & students.

**Status:** implemented

- [x] Every auditable action records its Campus (or School-level, for management actions)
- [x] A Campus Admin browsing the audit log sees only their own Campus's entries
- [x] The Superadmin sees all entries in their School, including School-level management actions
- [x] Single-school behavior is identical to today
- [x] Tests: seeded-scope service tests + route tests asserting the browse filter per role

## Comments

Built: `AuditService.log` stamps `campus_id` from the acting scope
(`campus_for_write(scope())`) — Campus-level actions land under their Campus,
school-level/system actions stay NULL. `list_entries`, `count`, and
`list_actions` now filter through `scoped_campus_filter` (own Campus + NULL
bucket for Campus-bound roles; every School Campus + NULL bucket for
School-bound roles) whenever a scope is active, so unscoped/system reads stay
unfiltered. The `/audit` route gates on the new
`require_admin_or_superadmin` dependency, and the sidebar shows "Audit log"
for both Admin and Superadmin (Settings stays Admin-only).

Verification: new `tests/test_audit_scope.py` (write stamping per role +
scoped browse/count/actions) and route tests in `tests/test_audit_routes.py`
(Superadmin browse, per-role browse filter, Owner 403, existing Finance 403
unchanged). Full suite green (804 tests); `mypy app` clean.

Commit: `d73406a`
