# 05 — Campus-scoped reports & campus dashboard

**What to build:** Scope the reporting surface to the acting user's Campus: the existing reports (income vs expense, arrears, expense by category, paid students, summarized finance, student register, all CSV exports) and the existing campus dashboard (KPI cards, charts, recent activity) reflect only the acting Campus's data. Campus staff see only their branch's figures; a School with two Campuses gets two independent sets of reports. Period dropdowns and paid/unpaid filters draw from the acting Campus's records only.

**Blocked by:** 04 — Per-campus fee policy and money flows.

**Status:** ready-for-agent

- [ ] Every report and CSV export reflects only the acting Campus's data
- [ ] The campus dashboard's KPIs, charts, and recent activity show only the acting Campus
- [ ] Report month dropdowns and paid-status filters draw only from the acting Campus's records
- [ ] Cross-Campus figures never leak into a Campus-bound user's output
- [ ] Single-school behavior is identical to today
- [ ] Tests: seeded-scope service tests + role-authenticated route tests with two Campuses
