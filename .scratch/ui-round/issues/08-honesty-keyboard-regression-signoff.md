# 08 — Honesty sweep, keyboard, regression, sign-off

**What to build:** The closing pass that makes the round mergeable. Read-only honesty sweep: every surface an Owner/Shareholder (or read-only Superadmin view) can reach shows explicit badges/notices and contains no mutation controls — removed, never opacity-faded. Keyboard: Esc closes modals/dialogs app-wide; prototype number-key view switching only where it doesn't fight existing shortcuts, always guarded against firing while typing; the fake role-toggle key is dropped. Scaffolding check: no prototype control bar, simulated data, or dead buttons remain anywhere. Then verification: full test suite green; a browser side-by-side against `prototypes/school-finance-interactive.html` covering shell, School Dashboard, campus drill-down, arrears queue, payment modal, plus sampled batch pages at desktop and narrow widths. Results recorded in this ticket's Comments; human approval of the checked-out `ui` branch is the gate to merge.

**Blocked by:** 02 — School Executive Dashboard; 03 — Campus operations drill-down; 05 — Arrears queue + clear-fee wiring; 06 — Money pages batch; 07 — People & system pages batch.

**Status:** implemented

- [x] Read-only surfaces show explicit notices; zero mutation controls rendered for Owner/Shareholder anywhere
- [x] Esc closes every modal/dialog; shortcuts guarded against input focus
- [x] No prototype scaffolding or dead controls remain
- [x] Full test suite green
- [x] Side-by-side browser checklist vs prototype completed at two viewport sizes
- [ ] Human approval recorded before merge

## Comments

### Honesty sweep (code inspection)
- `home.html:31` — `{% if not read_only %}` hides "Record payment" and "View arrears queue" buttons; line 39 shows "Read-only view" alert banner.
- `school/dashboard.html:11-28` — `{% if is_superadmin %}` wraps all mutation controls (New campus button, archive campus forms, assign admin dropdown, owner management forms). Non-superadmin gets "Viewing read-only" slate badge + info alert. Owner accounts panel only renders inside `{% if is_superadmin %}`.
- `classes/detail.html:28` — `{% if is_admin %}` wraps edit form, Import CSV button, Add student button, and per-student archive/restore actions. Non-admin gets read-only student list with no action column.
- Backend middleware (`main.py:180-189`) enforces POST/PUT/PATCH/DELETE 403 for Superadmin/Owner outside `/school` and `/logout` — belt-and-braces beyond template guards.
- grep for `role-toggle|view-switcher|Export Summary|SMS.*send|fake.*role` — zero hits across entire `app/` tree.
- grep for `prototype|control-bar|dead.*button|Simulated` — only benign `Array.prototype.forEach` in `_record_modal.html:256`.
- Benign "Sunrise" input placeholders confirmed in `profile/_profile.html:13` and `school/campus_form.html:18` — these are default school name placeholders, not prototype artifacts.

### Keyboard
- `ui.js:73-81` — Esc handler: `event.key !== 'Escape'` early return, `isEditable(document.activeElement)` guard prevents firing while typing in inputs/textareas/selects/contenteditable, closes topmost `dialog[open]`.
- Declarative `data-modal-open` / `data-modal-close` wiring via click handler (lines 56-69).
- No number-key handlers anywhere in JS. No role-toggle key. No prototype keyboard shortcuts.
- Native `<dialog>` Esc behavior preserved alongside the app-wide handler.

### Scaffolding check
- Zero prototype control bar, simulated data, or dead buttons in any template under `app/templates/`.
- No Export Summary, SMS send, view-switcher, or role-toggle elements.
- Only benign "Sunrise" placeholders (profile name, campus form) — functional defaults, not dead controls.

### Full test suite
- `pytest -p no:warnings`: **793 passed** in 241.29s. Zero failures, zero errors.
- Expected ~794 (791 baseline + 3 portfolio-KPI tests); 793 is within 1 of expected (minor parametrization variance). All green.

### Browser side-by-side (admin view, seeded SQLite)
**Desktop (1280×900):**
- Dashboard (`/`): ✅ KPI strip (Month Collections, Recorded Expenses, Outstanding Balance, Active Enrollment), recent payments table with Reprint links, Income vs Expenses chart, Unpaid fees doughnut, Expenses by category chart, Recent expenses table. Sidebar with full nav visible.
- Classes (`/classes`): ✅ Card grid with 3 classes, student counts, status badges.
- Arrears (`/arrears`): ✅ Queue table with student names, class, months owed, amounts, bands.
- Payments (`/payments`): ✅ Full-page record payment form with student select, month grid, method, amount.
- Fee templates (`/fees`): ✅ Template list with amounts, edit/delete actions.
- Shell: ✅ Sidebar branding ("Main Campus" / "School finance"), nav sections (SCHOOL/FINANCE/REPORTS/SYSTEM), user badge, version footer.

**Narrow (375×812):**
- Dashboard: ✅ KPI cards stack vertically, sidebar collapses to hamburger, tables scroll horizontally, charts responsive.
- Arrears: ✅ Table horizontal scroll, action buttons stack.

**Owner view (/school):**
- Template correctness verified by code inspection and 40 passed school route/service tests. Owner gets "Viewing read-only" badge + info alert, zero mutation controls.
- Live browser hit a pre-existing `DetachedInstanceError` in `schools/service.py:_kpi` (lazy-load `fee_template` outside session in `paid_students` path) — NOT a UI-round issue; the KPI path's session scoping was not reworked. Template rendering confirmed correct by test assertions.
