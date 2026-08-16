# 08 — School Dashboard: management, KPIs, and read-only owners

**What to build:** The Superadmin's working home and the read-only home of Owners/Shareholders (UR-9/12, C-10). From the School Dashboard the Superadmin creates Campuses (name and branding, details editable later by the Campus Admin), assigns a Campus Admin to each, creates and revokes Owner/Shareholder accounts, and archives a Campus (soft delete — closed branches keep their history). The dashboard summarizes every Campus as per-Campus KPI cards — collections, arrears, expenses, expected-vs-paid — with drill-down into any Campus's existing pages rendered read-only. The Superadmin sees every Campus's data read-only and never records or edits data. Owners see the same dashboard and drill-down read-only; every mutation path is refused for both Superadmin and Owner. Campus staff never see the dashboard — they keep the existing campus dashboard. The Campus Admin's user management is limited to creating and deactivating Finance Officers for their own Campus; they cannot create or promote Admins (or Owners). Prototype-first (R-5): the visual design of these screens is shown as a working browser prototype and approved before implementation.

**Blocked by:** 02 — Cloud setup wizard: School + Superadmin; 03 — Tenant scope plumbing + campus-scoped classes & students; 05 — Campus-scoped reports & campus dashboard.

**Status:** ready-for-agent

- [ ] A browser prototype of the School Dashboard, campus management, and owner view is shown and approved before implementation
- [ ] The Superadmin creates a Campus, assigns a Campus Admin, creates and revokes Owner accounts, and archives a Campus — each action audited as School-level
- [ ] Per-Campus KPI cards (collections, arrears, expenses, expected-vs-paid) render from each Campus's data; a two-Campus School is compared side by side
- [ ] Drill-down shows any Campus's existing pages read-only — no mutation available
- [ ] An Owner/Shareholder logs in to the read-only dashboard + drill-down; every mutating request is refused (403)
- [ ] The Superadmin never records or edits operational data
- [ ] A Campus Admin creates/deactivates Finance Officers for their own Campus only, and cannot create or promote Admins or Owners
- [ ] Campus staff never reach the School Dashboard
- [ ] Tests: role-authenticated TestClient flows (Superadmin management, Owner read-only/refusals, Campus Admin limitation, staff isolation)
