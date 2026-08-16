# 01 — Tenant schema reshape + single-school bootstrap

**What to build:** Add the tenant layer to the data model. A School owns one or more Campuses; every operational record — classes, students, fee templates, student amount changes, waivers, closed months, payments, credits, expense categories, expenses — carries a Campus, and the audit log carries a nullable Campus (school-level actions stay school-wide). Users gain a scope: School-scoped for Superadmin and Owner/Shareholder, Campus-scoped for Campus Admin and Finance Officer, and the role set grows to four values. The single-row school profile shape moves onto the Campus (name, logo, contact). The Campus carries an archive flag (soft delete — no hard deletes). This ticket is additive only: nothing is torn out, the old single-row profile is still read/written, `campus_id` columns are nullable, and every existing feature keeps working so the current suite stays green. Fresh installs bootstrap one School with one Campus silently — the offline path's first run behaves exactly as today, its data living in that implicit School + Campus.

**Blocked by:** None — can start immediately.

**Status:** implemented

- [x] Fresh databases create the schools, campuses (with profile fields + archive flag), scoped user columns, and the campus-scoped columns on every operational table; schema tests cover the new shape
- [x] A fresh single-school first run (one School, one Campus) bootstraps cleanly; the existing setup wizard, pages, and roles behave exactly as before
- [x] The existing full test suite stays green (additive-only schema, no removals)
- [x] No hard deletes introduced anywhere in the new tenant tables

## Comments

**Built (commit `3366322`):** additive-only tenant layer. Added `School` (id,
name) and `Campus` (school_id FK, name + the `school_profile` shape — address,
phone, email, website, logo_filename — plus the `archived` soft-delete flag) to
`app/models.py`; added a nullable, indexed `campus_id` FK + `campus` relationship
on every operational table (classes, students, fee_templates,
student_amount_changes, waivers, closed_months, payments, credits,
expense_categories, expenses, audit_log); added nullable `school_id`/`campus_id`
scope columns on `users`; grew `UserRoles` to four values (added `SUPERADMIN`,
`OWNER`). New `app/tenants/service.py` — `TenantService.ensure_bootstrap()`
creates the implicit School + first Campus idempotently (fresh DB → exactly one
of each; a School without a Campus gets its Campus added; existing tenants never
duplicated). Wired into `create_app`'s lifespan after `db.create_all()`, so the
offline first run behaves exactly as before with its data living in the implicit
School + Campus. The legacy single-row `school_profile` is untouched and still
read/written (per the ticket — nothing torn out).

**Verification:**
- New tests: 7 schema tests (four-role enum; campuses table shape + schools FK;
  archived soft-delete flag round-trip; `campus_id` nullable FK on every
  operational table incl. audit_log; users scope columns; operational row →
  campus round-trip) in `tests/test_schema.py`; 4 bootstrap tests in
  `tests/test_tenants_service.py` (one school + one campus, idempotent, repair
  of a school without a campus, no duplication of existing tenants); 1 app-level
  test in `tests/test_app.py` (startup bootstraps one school with one campus).
- Full suite: 640 passed (was 629 at baseline; +11 new). `mypy`: clean (53
  files). `scripts/seed_demo.py` still imports and compiles.
- The deleted screenshot PNGs that appeared mid-session were an external
  filesystem change, not from this work; restored from `HEAD` before committing.

**Notes for later tickets:** the silent bootstrap currently runs unconditionally
in the lifespan — correct while every deployment is a fresh SQLite file; when
the cloud path lands (ticket 02/09), tenant-key scoping replaces it so the setup
wizard (not a silent bootstrap) creates each School (UR-17, MD-1). MD-2's "one
FK per row" on `users` (role → school/campus scope) stays unenforced on purpose:
the schema is additive-only, so both columns are nullable for existing
single-school rows; enforcement belongs to the tenant-layer contract (ticket 09).
