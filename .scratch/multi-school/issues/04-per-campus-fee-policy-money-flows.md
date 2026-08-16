# 04 — Per-campus fee policy and money flows

**What to build:** Scope the fee and money-flow features to the Campus that owns the underlying student/class, following the pattern ticket 03 establishes. Fee templates, closed months, and expense categories are per-Campus (MD-3): a two-campus school duplicates its identical templates per Campus — copying on creation. Waivers and student amount changes attach only to students of the acting Campus. Payments and credits record only against the acting Campus's students, and expenses record only under the acting Campus's categories. Cross-campus ids are refused or return empty, never data.

**Blocked by:** 03 — Tenant scope plumbing + campus-scoped classes & students.

**Status:** ready-for-agent

- [ ] Fee templates are per-Campus: each Campus sees only its own templates; a template created in one Campus is invisible in another; a two-campus school duplicates "Standard — $100" per Campus
- [ ] Closed months and expense categories are per-Campus, so each branch sets its own fee policy and holidays
- [ ] Waivers and amount changes only ever target students of the acting Campus; a cross-campus target is refused
- [ ] Payments and credits record only against the acting Campus's students; a cross-campus payment is refused
- [ ] Expenses record only against the acting Campus's categories and data
- [ ] Single-school behavior is identical to today
- [ ] Tests: seeded-scope service tests + role-authenticated route tests with two Campuses
