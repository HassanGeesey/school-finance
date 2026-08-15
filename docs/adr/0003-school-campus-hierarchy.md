# 0003 — School → Campus hierarchy: campus owns everything operational, school is the umbrella

**Status:** accepted

The cloud path gains a tenant layer: a **School** contains one or more **Campuses** (1..N), and the Campus is the fully self-contained operational unit — its own profile/branding (name, logo, contact shown on receipts, sidebar, footer), closed months, fee templates, classes, students, expenses, and payments. The School exists only as the umbrella: the owner unit that campuses belong to, and the scope of ownership accounts. **Superadmin** (one per school, created with the school in the setup wizard) creates campuses, assigns each a Campus Admin, and creates the school's Owner/Shareholder accounts; Admin and Finance officer are scoped to exactly one campus and keep their single-school jobs; Owners/Shareholders see their school's campuses read-only, plus a per-campus summary dashboard. The offline .exe is untouched — it keeps the single-school model with no campus layer (UR-15).

The driver: the product will serve schools with real branches, and every role answer during grilling ("one school can have many campuses", "superadmin creates campuses and assigns an admin") treated the campus as the unit of everything. Even a one-branch school has a Campus from day one, so a second branch needs no migration and no per-campus deployment.

## Considered options

- **One global superadmin over all schools** (UR-13 first pass) — rejected: each school must own itself; a client school would never accept a platform operator as a tenant of its data.
- **School-wide branding with campus-scoped operations** (UR-14 b/c) — rejected: a two-campus school then inherits one brand and shared closed months/templates, making the second campus not a campus but a mirror; campus admins "doing the same job as right now" requires a fully self-contained unit.
- **Campus layer on the .exe too** — rejected ("don't change the school campus"): the offline path is one school on one machine; retrofitting the hierarchy adds migration and UI machinery with no user.
- **School → Campus → sub-units of classes only** (C-8's earlier reading, students-per-campus without branding) — superseded: branding must follow the operational unit, or receipts can't say which campus a parent pays.

## Consequences

- Every operational table gains `campus_id`; Schools gain their own table (`school_id` scope for ownership). The school_profile single row becomes the campus profile.
- Branding moves from "the one school" to per-campus: receipts, sidebar, and footer address the campus, not a school-level entity.
- Reports must roll up per campus and per school (owner dashboard = per-campus summaries + drill-down).
- The .exe and cloud paths diverge structurally at the data layer while sharing one codebase (D-1); the campus layer is cloud-only.
