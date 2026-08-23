# 03 — Campus operations drill-down

**What to build:** The campus drill-down becomes prototype view 2. A page header naming the Campus with its manager and active billing month; a 4-KPI strip (Month Collections with % of expected; Recorded Expenses; Outstanding Balance in amber with students-behind count; Active Enrollment); and the recent Month-tagged Payments ledger — student, class, month badge, method, time recorded, amount right-aligned bold emerald, and a receipt reprint action per row where the backend already provides it. The topbar campus selector pill lets school-scope users hop between campuses; breadcrumb reflects the School → Campus path; a back-to-School-Dashboard affordance stays obvious. Campus staff's own home adopts the same visual template without gaining any cross-campus visibility.

**Blocked by:** 01 — Token layer, component set, app shell.

**Status:** ready-for-agent

- [ ] KPI strip figures match existing service-computed values, `.num` tabular throughout
- [ ] Payments ledger renders month badges and right-aligned amounts on the ledger component
- [ ] Campus selector pill switches between campuses for school-scope users only
- [ ] Campus staff see identical data scope as today (isolation preserved)
- [ ] Route/scope tests pass unchanged

## Comments

-
