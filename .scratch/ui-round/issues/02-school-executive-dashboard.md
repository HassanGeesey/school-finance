# 02 — School Executive Dashboard

**What to build:** The School Dashboard becomes prototype view 1 on live data. A 4-KPI executive row (Total Collections with % of expected; Net Operating Flow after expenses; Outstanding Arrears in amber; Operating Campuses count with archived note and total active students), then the Campus Financial Health deck: one card per Campus with name + Active/Archived badge, manager line, collected/expenses/arrears stats row, expected-vs-paid progress bar with "collected of expected (%)" meta, and an enter-campus drill-down. Superadmin-only management affordances (campus creation, admin/owner management — which already exist functionally) are restyled into this layout; Archive appears only for the Superadmin on active campuses. Non-management roles see an explicit read-only viewing badge instead of controls. An archived Campus shows a preserved-records notice instead of stats and actions. Prototype-only affordances without backends (Export Summary) are omitted — no dead buttons.

**Blocked by:** 01 — Token layer, component set, app shell.

**Status:** implemented

- [x] Per-Campus cards show stats + progress bar with correct percentages; progress animates via transform, not width *(scaleX via CSS `calc(collected_percent / 100)`; percent comes from service)*
- [x] Drill-down reaches each active Campus; archived campus shows read-only notice with no drill-down actions
- [x] Management controls visible to Superadmin only; Owner/Shareholder gets explicit viewing badge and zero mutation controls
- [x] Existing campus/admin/owner provisioning flows still work after restyle
- [x] Route tests for role gating still pass unchanged
- [x] KPI row renders portfolio-wide figures computed in route/service context (no template arithmetic) *(resolved post-ticket: `SchoolDashboardService.portfolio_kpis()` added — see Comments)*

## Comments

- Rebuilt `app/templates/school/dashboard.html` as prototype view 1: page header (Superadmin: New campus primary action; Owner/Shareholder: explicit "Viewing read-only" slate badge) plus a read-only honesty notice containing the tested string "Read-only view". Executive 4-KPI row (Total Collections / Net Operating Flow / Outstanding Arrears amber / Operating Campuses with archived note + active students) renders from an optional `portfolio_kpis` context key — see FOUNDATION GAPS below.
- Campus Financial Health deck: 2-col grid of content-panels per Campus — name + Active/Archived badge, manager line, collected/expenses/arrears stats (`.num`, arrears amber when > 0), expected-vs-paid `.progress-wrap` bar animated via `transform: scaleX(calc(...))` (never width), meta "paid of expected (pct%)", and an Enter campus drill-down button (active campuses only).
- Archived campuses render a preserved-records notice instead of stats/actions/drill-down. Superadmin-only management restyled into card footers: Assign-campus-admin dropdown (admin-less active campuses) or Archive form (`data-confirm` dialog); archive gating logic unchanged (archive offered only where the old template offered it). Owner accounts panel kept for Superadmin with ledger-table styling; form fields/actions/labels byte-compatible.
- No Export Summary or other backendless affordances shipped. Zero arithmetic in templates (only comparisons like `arrears_cents > 0` for tone, as before).
- Verified: `pytest tests/test_school_routes.py -q -p no:warnings` → 19 passed; `pytest tests/test_tenant_scope.py -q -p no:warnings` → 18 passed (37 total). Owner-page assertions hold ("Read-only view" present; "Add owner"/"New campus" absent).
- Commit hash: not recorded — this agent was instructed not to run git commands; commit left to the coordinator.

Coordinator note: implementation committed as `3da88ee`; combined phase-2 verification run (school/reports/tenant/fees/expenses/reports-money/profile/classes/students/audit/admin/system/waivers/payments suites) = 308 passed. The portfolio-KPI gap stands as the ticket's one open item; resolution tracked below in this file once landed.

### FOUNDATION GAPS (route/service context needed)

1. **Portfolio KPI aggregates are absent from `GET /school` context** (app/schools/routes.py:75). The executive KPI row needs one context key, e.g. `portfolio_kpis` with: `total_collected_cents`, `total_expected_cents`, `collection_percent`, `net_flow_cents` (collected − expenses), `arrears_cents`, `active_campus_count`, `archived_campus_count`, `active_student_count` — summed over `SchoolDashboardService.list_campuses()` results in service/route context (guard `kpi is None`). Until it exists the row stays hidden; the template already renders it the moment the key appears.

Coordinator resolution (commit `c1bd250`): authorized minimal deviation from the round's "zero backend changes" guard — spec's own Implementation Decisions require these figures be computed in services/route context, which was impossible without them. Added frozen dataclass `PortfolioKpis` + `SchoolDashboardService.portfolio_kpis()` aggregating per-Campus KPIs, wired into `GET /school` context under exactly the key the template guards on. New tests: aggregation across campuses + archived-count handling (existing contracts untouched). test_school_service + test_school_routes = 40 passed; mypy delta vs pre-round baseline = zero. Ticket checklist now fully checked.
