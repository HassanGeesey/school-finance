# 02 — School Executive Dashboard

**What to build:** The School Dashboard becomes prototype view 1 on live data. A 4-KPI executive row (Total Collections with % of expected; Net Operating Flow after expenses; Outstanding Arrears in amber; Operating Campuses count with archived note and total active students), then the Campus Financial Health deck: one card per Campus with name + Active/Archived badge, manager line, collected/expenses/arrears stats row, expected-vs-paid progress bar with "collected of expected (%)" meta, and an enter-campus drill-down. Superadmin-only management affordances (campus creation, admin/owner management — which already exist functionally) are restyled into this layout; Archive appears only for the Superadmin on active campuses. Non-management roles see an explicit read-only viewing badge instead of controls. An archived Campus shows a preserved-records notice instead of stats and actions. Prototype-only affordances without backends (Export Summary) are omitted — no dead buttons.

**Blocked by:** 01 — Token layer, component set, app shell.

**Status:** ready-for-agent

- [ ] KPI row renders portfolio-wide figures computed in route/service context (no template arithmetic), all `.num` tabular
- [ ] Per-Campus cards show stats + progress bar with correct percentages; progress animates via transform, not width
- [ ] Drill-down reaches each active Campus; archived campus shows read-only notice with no drill-down actions
- [ ] Management controls visible to Superadmin only; Owner/Shareholder gets explicit viewing badge and zero mutation controls
- [ ] Existing campus/admin/owner provisioning flows still work after restyle
- [ ] Route tests for role gating still pass unchanged

## Comments

-
