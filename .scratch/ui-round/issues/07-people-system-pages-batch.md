# 07 — People & system pages batch re-skin

**What to build:** The people and system surfaces adopt the shared system: classes (index, detail, forms); students (index + student account — the owed-months ledger, waivers, month-tagged payments history, and Credit balance displayed with the indigo accent per DESIGN.md); audit log as a ledger; admin/settings page(s) including per-Campus branding controls. Search inputs, filters, and pagination restyled consistently; confirm dialogs/toasts shared. The student account is the deepest surface here — its expected-vs-paid-per-month story must stay legible with tabular numerals. Zero behavior change.

**Blocked by:** 01 — Token layer, component set, app shell.

**Status:** ready-for-agent

- [ ] Classes, students, student account, audit, settings render on the shared components
- [ ] Student account keeps per-month expected/paid/waiver/credit legibility with `.num` amounts
- [ ] Credit balances use the indigo accent consistently
- [ ] Admin/settings flows (including branding upload) still work
- [ ] Route tests for these areas pass unchanged

## Comments

-
