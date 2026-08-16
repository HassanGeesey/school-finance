# 01 — Tenant schema reshape + single-school bootstrap

**What to build:** Add the tenant layer to the data model. A School owns one or more Campuses; every operational record — classes, students, fee templates, student amount changes, waivers, closed months, payments, credits, expense categories, expenses — carries a Campus, and the audit log carries a nullable Campus (school-level actions stay school-wide). Users gain a scope: School-scoped for Superadmin and Owner/Shareholder, Campus-scoped for Campus Admin and Finance Officer, and the role set grows to four values. The single-row school profile shape moves onto the Campus (name, logo, contact). The Campus carries an archive flag (soft delete — no hard deletes). This ticket is additive only: nothing is torn out, the old single-row profile is still read/written, `campus_id` columns are nullable, and every existing feature keeps working so the current suite stays green. Fresh installs bootstrap one School with one Campus silently — the offline path's first run behaves exactly as today, its data living in that implicit School + Campus.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Fresh databases create the schools, campuses (with profile fields + archive flag), scoped user columns, and the campus-scoped columns on every operational table; schema tests cover the new shape
- [ ] A fresh single-school first run (one School, one Campus) bootstraps cleanly; the existing setup wizard, pages, and roles behave exactly as before
- [ ] The existing full test suite stays green (additive-only schema, no removals)
- [ ] No hard deletes introduced anywhere in the new tenant tables
