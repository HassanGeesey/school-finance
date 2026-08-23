# 08 — Honesty sweep, keyboard, regression, sign-off

**What to build:** The closing pass that makes the round mergeable. Read-only honesty sweep: every surface an Owner/Shareholder (or read-only Superadmin view) can reach shows explicit badges/notices and contains no mutation controls — removed, never opacity-faded. Keyboard: Esc closes modals/dialogs app-wide; prototype number-key view switching only where it doesn't fight existing shortcuts, always guarded against firing while typing; the fake role-toggle key is dropped. Scaffolding check: no prototype control bar, simulated data, or dead buttons remain anywhere. Then verification: full test suite green; a browser side-by-side against `prototypes/school-finance-interactive.html` covering shell, School Dashboard, campus drill-down, arrears queue, payment modal, plus sampled batch pages at desktop and narrow widths. Results recorded in this ticket's Comments; human approval of the checked-out `ui` branch is the gate to merge.

**Blocked by:** 02 — School Executive Dashboard; 03 — Campus operations drill-down; 05 — Arrears queue + clear-fee wiring; 06 — Money pages batch; 07 — People & system pages batch.

**Status:** ready-for-agent

- [ ] Read-only surfaces show explicit notices; zero mutation controls rendered for Owner/Shareholder anywhere
- [ ] Esc closes every modal/dialog; shortcuts guarded against input focus
- [ ] No prototype scaffolding or dead controls remain
- [ ] Full test suite green
- [ ] Side-by-side browser checklist vs prototype completed at two viewport sizes
- [ ] Human approval recorded before merge

## Comments

-
