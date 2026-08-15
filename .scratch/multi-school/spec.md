# Multi-school — spec

**Status:** ready-for-agent

Feature: multi-school / multi-campus tenant layer on the cloud path. Decisions: `project-decisions.md` → "Multi-school user roles grilling session" (UR-1..17), "Data-model round" (MD-1..3), "Cloud DB / multi-school" (C-1..10). Terms: `CONTEXT.md` → "Schools & campuses", "Users & roles". ADR: `docs/adr/0003-school-campus-hierarchy.md`.

## Problem Statement

The app serves one school on one machine. The user needs a cloud product where a **School** runs several **Campuses** (branches) with real role separation: a per-school **Superadmin** who provisions the school, its campuses, and its people; **Campus Admins** and **Finance Officers** who keep doing exactly their current single-school jobs, each inside one campus; and **Owners/Shareholders** who see all their school's data read-only with a per-campus summary dashboard. Today there is one role pair (admin/finance), one school, one profile, and zero tenant scoping — every table is global. The offline .exe must not change at all.

## Solution

A tenant layer: School → Campus (1..N); every operational table is scoped by `campus_id`; users carry a scope (school-level for Superadmin/Owner, campus-level for Admin/Finance). One central Supabase Postgres holds all schools; each school's deployment points at it. First run of a school deployment creates the School + its Superadmin (wizard); the Superadmin then creates Campuses, assigns each a Campus Admin, and creates Owner/Shareholder accounts from the **School Dashboard** — a per-campus KPI summary (collections, arrears, expenses, expected-vs-paid) with drill-down into any campus, read-only for Owners. Campuses own everything operational including branding (name/logo/contact on receipts and the app shell). The .exe keeps today's single-school model untouched.

## User Stories

1. As a first-run user on the cloud path, I want a setup wizard that names my school and creates its Superadmin, so that the school exists with an owner at the top before anything else happens.
2. As a Superadmin, I want to create Campuses for my School, so that each branch becomes its own manageable unit.
3. As a Superadmin, I want to assign a Campus Admin to each Campus, so that every branch has a manager.
4. As a Superadmin, I want to create Owner/Shareholder accounts, so that shareholders can see school performance.
5. As a Superadmin, I want to revoke Owner/Shareholder and Campus Admin access, so that people who leave stop seeing data.
6. As a Superadmin, I want to view every Campus's data read-only, so that I can monitor the school without touching records.
7. As a Superadmin, I want the School Dashboard to summarize each Campus, so that I can compare branches at a glance and drill into any of them.
8. As an Owner/Shareholder, I want read-only access to every Campus of my School, so that I can monitor the business as a stakeholder.
9. As an Owner/Shareholder, I want the same summary dashboard with drill-down, so that I can investigate without the power to alter anything.
10. As an Owner/Shareholder, I want every mutation path (record payment, add student, edit anything) unavailable to me, so that I can never change data by accident.
11. As a Campus Admin, I want to manage my Campus exactly as today — classes, students, fee templates, waivers, closed months, expenses, payments, reports, settings — so that my day-to-day job is unchanged.
12. As a Campus Admin, I want zero visibility of other Campuses, so that branches stay isolated.
13. As a Campus Admin, I want to create and deactivate Finance Officers for my Campus only, so that I can staff my branch.
14. As a Campus Admin, I want to be unable to create or promote Admins (or Owners), so that only the Superadmin appoints managers.
15. As a Campus Admin, I want to edit my Campus's branding — name, logo, contact — so that receipts, the sidebar, and the footer address my branch.
16. As a Finance Officer, I want to record payments and expenses and run reports exactly as today, scoped to my Campus, so that my job is unchanged.
17. As a Campus Admin or Finance Officer, I want the existing campus-level dashboard and pages to behave as they do today, so that nothing regresses for staff.
18. As a Campus Admin, I want fee templates, closed months, and expense categories to be per-Campus, so that each branch sets its own fee policy and holidays.
19. As a Campus Admin, I want to archive a Campus (soft delete) from the Superadmin side, so that closed branches keep their history.
20. As the Superadmin, I want the audit log to record school-level actions (campus creation, admin assignment, owner management), so that accountability follows the scope.
21. As a Campus Admin, I want the audit log to record campus-level actions, so that accountability stays with the branch.
22. As the .exe operator, I want the offline app to behave exactly as before — same wizard, same pages, same roles — so that single-machine schools see zero change.
23. As a School with two Campuses, I want both branches' data in the one database and dashboard, so that the owner can compare them side by side.

## Implementation Decisions

- **Tenant hierarchy:** new `schools` table (id, name) → new `campuses` table (id, school_id FK, name + the profile fields that `school_profile` carries today: name, logo_filename, address, phone, email, website). The single-row `school_profile` becomes the per-Campus profile (UR-14).
- **Scope columns (MD-2):** `campus_id` on every operational table — students, classes, fee_templates, student_amount_changes, waivers, closed_months, payments, credits, expense_categories, expenses, audit_log (nullable on audit_log for school-level actions). The School is reached by campus → school join; no denormalized `school_id` on operational tables.
- **Users & roles:** `users` gains scope columns — `school_id` for Superadmin and Owner/Shareholder, `campus_id` for Admin and Finance Officer — plus the role enum extended to four values. `sessions` stays unscoped: the user row resolves the scope per request.
- **Scoping mechanism:** a per-request scope object (school + campus) is resolved from the authenticated user in the request pipeline and threaded into services; every tenant query filters by it. (Note: the existing `get_db` dependency is unwired — services open their own sessions — so the scope travels with the request/user, not via `get_db`.) Any unscoped query is a bug; cross-scope access returns empty/404, never data.
- **Provisioning (UR-17):** cloud first run — the setup wizard creates the School (name) + Superadmin account in one step; the Superadmin then creates Campuses, assigns each a Campus Admin, and creates Owner/Shareholder accounts from the School Dashboard. No operator-side provisioning.
- **School Dashboard (UR-9/UR-12):** per-Campus KPI cards (collections, arrears, expenses, expected-vs-paid) with drill-down into any Campus's read-only data. Home of the Superadmin; read-only home of Owners. Campus staff never see it — they keep the existing campus dashboard.
- **Permissions:** Superadmin — management (campuses, admins, owners) + read-only data everywhere (UR-2). Campus Admin — today's Admin job, one campus, may create/deactivate Finance Officers only (UR-11). Finance Officer — today's job, one campus. Owner/Shareholder — read-only everywhere in their School, all mutations refused (UR-3/UR-16).
- **Fee policy (MD-3):** fee templates are per-Campus; a two-campus School duplicates identical templates per Campus. Closed months and expense categories are per-Campus too (UR-14).
- **The .exe (UR-15, C-5):** unchanged — same wizard, pages, and roles (Admin/Finance). Under the shared schema its data belongs to one School with one Campus, created silently at first run; no visible change, one codebase (D-1).
- **Database (MD-1, C-7):** one central Supabase Postgres (DB-only); each school's deployment points at it. RLS is a follow-up (C-3). The offline path stays SQLite.

## Testing Decisions

- **Primary seam — HTTP routes:** role-authenticated `TestClient` flows asserting external behavior: a Campus Admin's request for another Campus's student/payment/expense returns nothing (404/empty), an Owner's mutating request is refused, a Superadmin sees every Campus and creates campuses/admins/owners, a Finance Officer's endpoints behave as today inside one campus. Prior art: `tests/test_*_routes.py` with the `mini_app`/`client` fixtures (in-memory SQLite).
- **Secondary seam — service layer:** the scoping/filter logic and role checks live in services; test them directly with a seeded scope. Prior art: `tests/test_*_service.py`.
- **Schema:** new tables/columns and the per-campus profile shape, `.exe` first-run still bootstraps cleanly. Prior art: `tests/test_schema.py`.
- **Good tests assert behavior, not implementation:** "owner cannot record a payment" not "the payments route checks role X at line Y"; "admin sees only campus 1's students" not "the query has a WHERE campus_id".
- **Regression:** the full existing suite (629 tests) stays green — the single-school .exe paths must not regress.

## Out of Scope

- **Deployment/architecture round** (per C-9): per-school containers, tenant keys in env, Dokploy/compose changes, Secure-cookie and shutdown-flag follow-ups. Later round, not this build.
- **Visual design of the new screens** (School Dashboard, campus management, owner view): prototype-first per R-5 — a working browser prototype is shown and approved before implementation.
- **Postgres RLS** — follow-up ticket (C-3).
- **Data migration** — no live multi-school data exists; existing single-school deployments are untouched.
- **.exe changes** — explicitly out (UR-15).
- **Global superadmin / platform operator** — rejected (UR-13): each school owns itself.

## Further Notes

- Glossary updated: `CONTEXT.md` → "Schools & campuses" (School, Campus) and "Users & roles" (Superadmin, Campus Admin, Finance Officer, Owner/Shareholder, School Dashboard).
- ADR: `docs/adr/0003-school-campus-hierarchy.md` (accepted) — campus owns everything operational incl. branding; school is the umbrella.
- Decision log: `project-decisions.md` UR-1..17 (roles), MD-1..3 (data model), C-1..10 (cloud DB context).
- The fee-billing model (owed months, waivers, month-tagged payments, credit) is unchanged — it becomes campus-scoped, not redesigned.
