# 03 — Tenant scope plumbing + campus-scoped classes & students

**What to build:** The scoping mechanism: a per-request scope (the School, plus the Campus when the user is Campus-bound) is resolved from the authenticated user in the request pipeline and threaded into the class and student services, so every query filters by it. A Campus Admin or Finance Officer sees only their own Campus's classes and students — a request for another Campus's record returns 404/empty, never data. Cross-scope mutations (edit, archive, restore, amount change, import) are refused the same way. All four roles are recognized by the auth gates, so a Superadmin or Owner logging in is not blocked. The single-school deployment is behaviorally identical — its one Campus is the scope. The classes and students feature is the first one scoped here; the other operational features are scoped in tickets 04–07 following the same pattern.

**Blocked by:** 01 — Tenant schema reshape + single-school bootstrap.

**Status:** implemented

- [x] A Campus Admin/Finance Officer sees only their Campus's classes and students (lists, search, detail)
- [x] A request for another Campus's class or student returns 404/empty
- [x] A Campus Admin's mutations (create, edit, archive, restore, amount change, CSV import) only ever touch their own Campus's records
- [x] Superadmin and Owner users resolve a School-wide scope and are recognized at login (no false 403)
- [x] Single-school behavior is identical to today (implicit one-Campus scope)
- [x] Tests: seeded-scope service tests + role-authenticated route tests with two Campuses

## Comments

**Built (commit `d967725`):** the per-request scope seam (owned by the
coordinator, I-2/I-3). `app/tenants/scope.py` — `RequestScope(user, school_id,
campus_id)` frozen dataclass; `RequestScope.for_user(user)` returns `None` for
anonymous AND for legacy users with both scope columns `None` (keeps unbound
finance users unscoped → legacy behavior); `scope()` contextvar;
`scope_context(...)`; `scoped_campus_filter(session, scope, column)` (OR incl.
`column.is_(None)` so NULL-campus legacy rows stay visible to every scope);
`in_scope(session, scope, campus_id)`; `campus_for_write(scope)` for new-row
stamps. Wired in `app/auth/deps.py` (`current_user` resolves the scope) and the
session middleware in `app/main.py` (`scope_context(...)` around `await
call_next`). `require_login` recognizes all four roles; `require_admin` stays
Admin-only for mutations.

Campus scoping on classes/students: `ClassService`/`StudentService` read
`scope()` once per method; lists/search apply `scoped_campus_filter`; single-row
lookups (`_get_class`, `_get_class_with_template`, `_get_student`,
`_get_template`) raise NotFound / "Choose a valid fee template." via `in_scope`;
new rows (`Class`, `Student`, `StudentAmountChange`) are stamped with
`campus_for_write(scope())`. Cross-campus mutations and foreign-campus template
use are refused the same way. A School-scoped Superadmin sees both Campuses; the
single-school deployment behaves identically (its one Campus is the scope;
NULL-campus legacy rows remain visible — hardening is ticket 09).

**Verification:**
- New tests: `tests/test_tenant_scope.py` — 18 seeded two-campus service tests
  (isolation of lists/search/detail/student counts, foreign-campus 404s,
  create/import/amount-change campus stamping, foreign-campus template
  rejection, cross-campus mutation refusal, Superadmin sees both, per-role scope
  resolution). Route-level: `tests/test_classes_routes.py` +
  `tests/test_students_routes.py` — two-campus login flows via the role-
  authenticated TestClient.
- Full suite: 666 passed. `mypy` clean (only the pre-existing pystray errors in
  `app/desktop/launcher.py:278` remain).

**Notes for later tickets:** the other operational features (fee templates,
payments, expenses, …) are scoped in tickets 04–07 following this same pattern.
`RequestScope.for_user` short-circuits legacy users (both columns None) to
unscoped — the MD-2 enforcement that every user is bound belongs to ticket 09.
