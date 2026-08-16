# 09 — Tenant-layer contract (scope is mandatory)

**What to build:** Tighten the tenant layer from additive to mandatory. `campus_id` becomes NOT NULL on every operational table now that every insert path sets it. Every service query carries the scope — no unscoped path remains; any unscoped query is a bug. Cross-scope access returns empty/404 by construction, never data. This is the final hardening pass: sweep the services for unscoped queries, tighten the schema constraints, and run the full regression including the single-school deployment.

**Blocked by:** 04 — Per-campus fee policy and money flows; 05 — Campus-scoped reports & campus dashboard; 06 — Campus-scoped audit log; 07 — Per-campus branding.

**Status:** ready-for-agent

- [ ] `campus_id` is NOT NULL on every operational table and every insert path sets it
- [ ] A sweep finds no unscoped query paths in the services (scope is required by construction)
- [ ] Cross-scope access returns 404/empty across the whole surface
- [ ] The full existing suite (629 tests) plus the new multi-school tests are green
- [ ] The single-school offline deployment behaves exactly as before (implicit one-Campus scope)
