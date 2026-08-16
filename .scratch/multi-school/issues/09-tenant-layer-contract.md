# 09 — Tenant-layer contract (scope is mandatory)

**What to build:** Tighten the tenant layer from additive to mandatory. `campus_id` becomes NOT NULL on every operational table now that every insert path sets it. Every service query carries the scope — no unscoped path remains; any unscoped query is a bug. Cross-scope access returns empty/404 by construction, never data. This is the final hardening pass: sweep the services for unscoped queries, tighten the schema constraints, and run the full regression including the single-school deployment.

**Blocked by:** 04 — Per-campus fee policy and money flows; 05 — Campus-scoped reports & campus dashboard; 06 — Campus-scoped audit log; 07 — Per-campus branding.

**Status:** implemented

- [x] `campus_id` is NOT NULL on every operational table and every insert path sets it
- [x] A sweep finds no unscoped query paths in the services (scope is required by construction)
- [x] Cross-scope access returns 404/empty across the whole surface
- [x] The full existing suite plus the new multi-school tests are green
- [x] The single-school offline deployment behaves exactly as before (implicit one-Campus scope)

## Comments

**What was built** (ticket 09 — tenant layer made mandatory):

- `app/models.py`: `campus_id` is now NOT NULL on the ten operational data tables
  (`classes`, `students`, `fee_templates`, `student_amount_changes`, `waivers`,
  `closed_months`, `payments`, `credits`, `expense_categories`, `expenses`). The
  two deliberate nullable exceptions stay nullable: `audit_log.campus_id`
  (school-level events are school-wide, MD-2) and `users.school_id`/`campus_id`
  (Admin/Finance scope by Campus, Superadmin/Owner by School).
- `app/tenants/scope.py`: added `TenantScopeError`, `require_scope()`, and a
  strict `audit_scope_filter` (the audit NULL bucket). `campus_for_write()` now
  raises unless a Campus-bound scope is active, `scoped_campus_filter()` drops
  the legacy NULL inclusion and raises on an unscoped call, and `in_scope()`
  returns False for unscoped/Null rows.
- Service sweep: every operational service (`classes`, `students`, `fees`,
  `payments`, `expenses`, `arrears`, `reports`) now calls `require_scope()`
  instead of the old `if cur is not None` guard, so an unscoped read/write fails
  loudly instead of leaking. `admin/service.py` stamps `create_user` with the
  acting scope's `school_id`/`campus_id` and scopes user management to the
  acting Campus/School. The audit service keeps the MD-2 carve-out (school-level
  entries stay NULL and visible alongside campus entries), so the single-school
  audit page is unchanged.
- Tests: `tests/conftest.py` adds a `world` fixture (implicit School + Campus +
  default scope) and a `campus_id` fixture; service tests opt in via an autouse
  `_scoped` fixture; `tests/helpers.py` binds the finance user and stamps the
  billing fixtures, and adds `in_admin_scope` for route-test seeding; the scope
  test files drop all legacy NULL-campus rows; `test_schema.py` asserts NOT NULL
  on the ten operational tables, the audit_log nullable carve-out, and that an
  orphan row is rejected. New `tests/test_tenant_scope_contract.py` pins the
  mandatory contract (unscoped reads/writes raise `TenantScopeError`).

**Verification:** full suite green (743 baseline + multi-school + the new
contract tests), `mypy app` clean for all touched modules (5 remaining errors
are in the in-progress `app/schools/` / `app/main.py` work, not this ticket).

**Commit:** `1548785`
