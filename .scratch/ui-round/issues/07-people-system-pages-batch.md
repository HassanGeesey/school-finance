# 07 — People & system pages batch re-skin

**What to build:** The people and system surfaces adopt the shared system: classes (index, detail, forms); students (index + student account — the owed-months ledger, waivers, month-tagged payments history, and Credit balance displayed with the indigo accent per DESIGN.md); audit log as a ledger; admin/settings page(s) including per-Campus branding controls. Search inputs, filters, and pagination restyled consistently; confirm dialogs/toasts shared. The student account is the deepest surface here — its expected-vs-paid-per-month story must stay legible with tabular numerals. Zero behavior change.

**Blocked by:** 01 — Token layer, component set, app shell.

**Status:** implemented

- [x] Classes, students, student account, audit, settings render on the shared components
- [x] Student account keeps per-month expected/paid/waiver/credit legibility with `.num` amounts
- [ ] Credit balances use the indigo accent consistently *(credit rendering lives in `fees/_account_finance.html` + payments partials — owned by ticket 06; flagged as cross-scope)*
- [x] Admin/settings flows (including branding upload) still work
- [x] Route tests for these areas pass unchanged

## Comments

- Built: classes index/detail/form on ledger tables (`amount-head`/`amount-cell`, `primary-cell`, `.num` counts), KPI value block replacing the ad-hoc `text-3xl` fee figure, add-student + add-waiver modals rebuilt on shared `modal-header/body/footer` anatomy (open/close via ui.js declarative `data-modal-open`/`data-modal-close`); record-payment button moved to the emerald accent per DESIGN.md. Students search filters restyled onto `content-panel` + `label/label-text` (dead `frow`/`label-t` legacy classes replaced where superseded); import form/report, edit form on panels; status badge macros canonicalized to emerald/slate/indigo. Audit filter panelled, timestamps `.num`, pagination numbered `.num`. Admin `_users` avatars/badges/reset-dropdown cleaned to token components (htmx payloads byte-identical); `_backups` table on ledger cells with overflow-x-auto (JS toggle hooks `#backup-show-all`/`.backup-row-more`/chevron/label preserved verbatim); shutdown + shutdown-disabled standalone pages wear `content-panel` + warning icon; profile branding partial kept flow-identical (only dead `file-input-bordered` class dropped). Zero template arithmetic added; no dead buttons; visible text asserted by tests preserved.
- Verification: `pytest tests/test_classes_routes.py tests/test_students_routes.py tests/test_audit_routes.py tests/test_admin_routes.py tests/test_system_routes.py tests/test_waivers_routes.py -q -p no:warnings` → 117 passed; `tests/test_profile_routes.py -q -p no:warnings` → 22 passed. Tests untouched; no backend changes.
- Foundation gaps: (1) credit-balance indigo accent belongs to `fees/_account_finance.html`/payments partials (ticket 06 scope — currently emerald `badge-success` "Credit"); (2) no shared file-input styling in the token layer beyond the compiled daisyUI-compat artifact; (3) `select-bordered`/`file-input-bordered` were dead classes in old markup — dropped here, other batches may still carry them.
- Commit: withheld — ticket executed under an explicit no-git-commands constraint; work left uncommitted on branch `ui`.

Coordinator note: implementation committed as `a276b08`; included in the 308-passed combined phase-2 run. Gap (1) resolved by ticket 06's coordinator pass (credit indigo in `fees/_account_finance.html`); gaps (2)/(3) folded into ticket 08 sweep.
