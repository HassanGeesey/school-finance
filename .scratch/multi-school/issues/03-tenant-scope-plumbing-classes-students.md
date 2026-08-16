# 03 — Tenant scope plumbing + campus-scoped classes & students

**What to build:** The scoping mechanism: a per-request scope (the School, plus the Campus when the user is Campus-bound) is resolved from the authenticated user in the request pipeline and threaded into the class and student services, so every query filters by it. A Campus Admin or Finance Officer sees only their own Campus's classes and students — a request for another Campus's record returns 404/empty, never data. Cross-scope mutations (edit, archive, restore, amount change, import) are refused the same way. All four roles are recognized by the auth gates, so a Superadmin or Owner logging in is not blocked. The single-school deployment is behaviorally identical — its one Campus is the scope. The classes and students feature is the first one scoped here; the other operational features are scoped in tickets 04–07 following the same pattern.

**Blocked by:** 01 — Tenant schema reshape + single-school bootstrap.

**Status:** ready-for-agent

- [ ] A Campus Admin/Finance Officer sees only their Campus's classes and students (lists, search, detail)
- [ ] A request for another Campus's class or student returns 404/empty
- [ ] A Campus Admin's mutations (create, edit, archive, restore, amount change, CSV import) only ever touch their own Campus's records
- [ ] Superadmin and Owner users resolve a School-wide scope and are recognized at login (no false 403)
- [ ] Single-school behavior is identical to today (implicit one-Campus scope)
- [ ] Tests: seeded-scope service tests + role-authenticated route tests with two Campuses
