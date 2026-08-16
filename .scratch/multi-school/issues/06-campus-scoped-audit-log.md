# 06 — Campus-scoped audit log

**What to build:** Audit entries carry the scope of the action (US-20/21). Campus-level actions — payments, expenses, students, classes, fee templates, waivers, closed months, branding — are tagged to the Campus they happened in; school-level actions — Campus creation, Campus Admin assignment, Owner management — are tagged School-wide (nullable Campus). The audit browser shows only what the actor may see: a Campus Admin browses their own Campus's entries; the Superadmin browses every entry in their School, including school-level ones.

**Blocked by:** 03 — Tenant scope plumbing + campus-scoped classes & students.

**Status:** ready-for-agent

- [ ] Every auditable action records its Campus (or School-level, for management actions)
- [ ] A Campus Admin browsing the audit log sees only their own Campus's entries
- [ ] The Superadmin sees all entries in their School, including School-level management actions
- [ ] Single-school behavior is identical to today
- [ ] Tests: seeded-scope service tests + route tests asserting the browse filter per role
