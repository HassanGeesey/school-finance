# 08 — School Dashboard: management, KPIs, and read-only owners

**What to build:** The Superadmin's working home and the read-only home of Owners/Shareholders (UR-9/12, C-10). From the School Dashboard the Superadmin creates Campuses (name and branding, details editable later by the Campus Admin), assigns a Campus Admin to each, creates and revokes Owner/Shareholder accounts, and archives a Campus (soft delete — closed branches keep their history). The dashboard summarizes every Campus as per-Campus KPI cards — collections, arrears, expenses, expected-vs-paid — with drill-down into any Campus's existing pages rendered read-only. The Superadmin sees every Campus's data read-only and never records or edits data. Owners see the same dashboard and drill-down read-only; every mutation path is refused for both Superadmin and Owner. Campus staff never see the dashboard — they keep the existing campus dashboard. The Campus Admin's user management is limited to creating and deactivating Finance Officers for their own Campus; they cannot create or promote Admins (or Owners). Prototype-first (R-5): the visual design of these screens is shown as a working browser prototype and approved before implementation.

**Blocked by:** 02 — Cloud setup wizard: School + Superadmin; 03 — Tenant scope plumbing + campus-scoped classes & students; 05 — Campus-scoped reports & campus dashboard.

**Status:** implemented

- [ ] A browser prototype of the School Dashboard, campus management, and owner view is shown and approved before implementation
- [x] The Superadmin creates a Campus, assigns a Campus Admin, creates and revokes Owner accounts, and archives a Campus — each action audited as School-level
- [x] Per-Campus KPI cards (collections, arrears, expenses, expected-vs-paid) render from each Campus's data; a two-Campus School is compared side by side
- [x] Drill-down shows any Campus's existing pages read-only — no mutation available
- [x] An Owner/Shareholder logs in to the read-only dashboard + drill-down; every mutating request is refused (403)
- [x] The Superadmin never records or edits operational data
- [x] A Campus Admin creates/deactivates Finance Officers for their own Campus only, and cannot create or promote Admins or Owners
- [x] Campus staff never reach the School Dashboard
- [x] Tests: role-authenticated TestClient flows (Superadmin management, Owner read-only/refusals, Campus Admin limitation, staff isolation)

## Comments

Built: a new `app/schools/` module (service + routes) behind the existing
Campus-scoped services. `SchoolDashboardService` owns the School-level facts
the Campus services never see: the School's Campuses (create with optional
first Campus admin, assign a Campus admin later, archive with a last-active-
Campus guard), the Owner accounts (create/disable/enable), and the per-Campus
KPI cards (collections, expenses, arrears, expected-vs-paid, active students)
computed by running the report service under each Campus's scope so a two-
Campus School is compared side by side. Routes: `GET /school` dashboard +
Superadmin-only management POSTs (`/school/campuses`, `/school/campuses/{id}/admin`,
`/school/campuses/{id}/archive`, `/school/owners`, `/school/owners/{id}/disable|enable`),
and read-only drill-down `GET /campuses/{id}/...` that reuses each existing page
handler (dashboard, students, classes, fees, payments, expenses, arrears,
reports + CSVs) under a Campus-scoped context — nothing is ever written. The
session middleware returns 403 to every non-`/school` mutation from a
School-bound account, `/` redirects Superadmin/Owner to `/school`, and the
shell nav/branding render the School-bound and viewing-Campus states.
`AdminUserService` now limits a Campus-bound Admin to creating and managing
Finance Officers of their own Campus (role picker restricted too); new
school-level `AuditActions` record Campus/Owner lifecycle entries with a NULL
Campus (MD-2). Also fixed two latent detached-instance bugs the drill-down
exposed: `ArrearsService.arrears_report` processed students after its session
closed, and `ReportService.student_status_rows` lazy-loaded on detached
students (now re-attached via `session.merge`). The prototype-first step
(R-5) was waived in favour of direct implementation at the user's direction.

Verification: new `tests/test_school_service.py` (Campus/Owner lifecycle,
audit, KPI isolation) and `tests/test_school_routes.py` (Superadmin
management, Owner read-only + 403s, Campus Admin finance-only clamp, staff
isolation, read-only drill-down isolation); `tests/test_admin_*` updated for
the Campus Admin limitation. Full suite green (791 tests).

Commit: `daf8cea`
