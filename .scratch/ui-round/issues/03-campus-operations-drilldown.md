# 03 — Campus operations drill-down

**What to build:** The campus drill-down becomes prototype view 2. A page header naming the Campus with its manager and active billing month; a 4-KPI strip (Month Collections with % of expected; Recorded Expenses; Outstanding Balance in amber with students-behind count; Active Enrollment); and the recent Month-tagged Payments ledger — student, class, month badge, method, time recorded, amount right-aligned bold emerald, and a receipt reprint action per row where the backend already provides it. The topbar campus selector pill lets school-scope users hop between campuses; breadcrumb reflects the School → Campus path; a back-to-School-Dashboard affordance stays obvious. Campus staff's own home adopts the same visual template without gaining any cross-campus visibility.

**Blocked by:** 01 — Token layer, component set, app shell.

**Status:** implemented

- [x] KPI strip figures match existing service-computed values, `.num` tabular throughout *(Month Collections % of expected omitted — value not exposed by dashboard_context; see Comments)*
- [x] Payments ledger renders month badges and right-aligned amounts on the ledger component
- [x] Campus selector pill switches between campuses for school-scope users only
- [x] Campus staff see identical data scope as today (isolation preserved)
- [x] Route/scope tests pass unchanged

## Comments

Built (`app/templates/home.html`, commit `919ba33`): page header names the Campus with manager/billing-month area and an explicit "Back to School dashboard" action plus read-only alert for school-bound viewers; 4-KPI strip on `.kpi-value num` cards (Month Collections, Recorded Expenses, Outstanding Balance amber, Active Enrollment); recent Month-tagged Payments ledger on content-panel/ledger components — student, class, month badge (`badge-slate num`), method, time recorded, emerald right-aligned `amount-cell num` amounts, per-row receipt Reprint linking to the existing GET /payments/{id}/receipt. Campus selector pill and School→Campus breadcrumbs come from the ticket-01 shell and render for school-scope users only; campus staff "/" home uses the identical template with no cross-campus data paths.

Foundation gaps (context values absent; omitted rather than computed in template): (1) "% of expected" for Month Collections — DashboardData exposes no expected_cents/percentage; meta falls back to "Payments recorded this month"; (2) students-behind total would be template arithmetic from arrears_band_counts, so per-band counts render instead ("N over 60 days · N 31–60 · N current"); (3) campus manager name not in Campus model/context — "Managed by" line omitted (adding it means schema change, out of round scope); (4) no period-label helper — month badges render MM/YYYY numeric.

Verification: test_school_routes + test_reports_scope_routes = 35 passed; test_tenant_scope = 18 passed; extra regression sweep (reports/app/profile) = 56 passed — all unchanged. Included in coordinator's combined phase-2 run: 308 passed.
