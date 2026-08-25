# School Finance Premium Dashboard — implementation spec

Status: ready for implementation

This spec translates `prototypes/school-finance-premium.html` into the real multi-school dashboard at `app/templates/school/dashboard.html`. It is a UI/layout change only. Existing routes, permissions, audit behavior, money calculations, and tenant scoping remain the source of truth.

## Design direction

The direction is “Private Office”: calm, editorial, and finance-led. The surface should feel like a trusted finance console rather than a generic admin panel.

Principles:

1. **Numbers carry the hierarchy.** Put the current period and the most decision-relevant financial figure first. Use generous whitespace, tabular numerals, right-aligned amounts, and short labels.
2. **Quiet confidence.** Use a warm light canvas, a dark navigation rail, hairline rules, restrained radius, and no gradients, decorative illustrations, or dense card chrome.
3. **Decisions over decoration.** Each campus summary should answer: what is the position, what needs attention, who owns it, and where can I go next?
4. **One visual language.** Use the same spacing, rule, label, amount, status, and action treatments across campus cards and owner accounts.
5. **Trust through precision.** Never imply that a derived KPI is a ledger balance. Label the period, show the source context, and preserve the app’s existing money formatting.
6. **Keep the school dashboard multi-campus.** The prototype’s single-school sample becomes a portfolio-style overview of campuses, with each campus as a focused “office” block.

## Exact three-color system

Use only these three brand colors in the premium dashboard. Do not introduce a fourth accent color.

| Token | Hex | Use |
|---|---:|---|
| `--sf-ink` | `#0D1B2A` | Navigation rail, primary text, primary buttons, rules, high-emphasis data |
| `--sf-paper` | `#F6F2EA` | Page canvas, rail text, inverse text, warm empty space |
| `--sf-lime` | `#D8F36A` | Active navigation, selected/positive emphasis, progress fill, one featured KPI surface, focus ring |

Derived treatments must be transparency or grayscale mixing from these tokens, not new hues. Semantic states must also include explicit text/icons so color is never the only signal.

## Layout structure

Use the existing `base.html` shell. The premium treatment belongs inside the authenticated layout; do not create a second page shell.

Desktop (`>= 1024px`) keeps the dark rail, warm paper work area, thin topbar rule, editorial intro, and a single-column campus decision ledger. Each campus row contains identity/admin context, four KPIs, expected-vs-paid progress, and the existing action links. Owner accounts remain below the campus activity and are visually subordinate.

Mobile (`< 768px`) keeps the existing collapsible rail. Stack the intro and action, make each campus full width, use a 2×2 KPI grid, wrap actions, and stack owner-account fields. Do not hide primary dashboard, payment, arrears, or report routes.

Add stable hooks such as `sf-dashboard`, `sf-intro`, `sf-campus-row`, `sf-kpi-strip`, `sf-progress`, `sf-campus-actions`, and `sf-owner-ledger`.

## Components

### Premium shell

Restyle the existing shell selectors: `#app-sidebar` / `.index-brand` use ink; `.nav-link` uses muted inverse text with a lime active marker; `#app-topbar` uses paper with a bottom rule; `main` uses the paper canvas and prototype-aligned gutters. Keep the existing navigation branches, sidebar toggle/backdrop, search, user dropdown, scripts, footer, and confirmation dialog.

### Portfolio intro

Use an eyebrow such as `School overview`, a large calm headline, short supporting copy, period context, and the current superadmin-gated `New campus` action. Do not hard-code the prototype’s sample net position or movement. If no aggregate position exists in the route context, keep the intro descriptive.

### Campus decision row

Preserve and visually prioritize:

- `summary.campus` / `c.name` / `c.archived`
- `summary.admin.name` and `summary.admin.username`
- `summary.kpi.collected_cents`
- `summary.kpi.expenses_cents`
- `summary.kpi.arrears_cents`
- `summary.kpi.active_student_count`
- `summary.kpi.paid_cents`
- `summary.kpi.expected_cents`
- `summary.kpi.collected_percent`

Order the row as identity → KPI strip → paid/expected progress → navigation/actions → admin mutations. Use `money()` for all cents values and the supplied percentage for progress. Keep archived campuses visible and openable. Keep archive confirmation and assign-admin forms unchanged in behavior.

### States

Retain the current distinctions: reporting unavailable, no activity, no campuses, archived, and read-only. Style them quietly, but keep visible text and accessible semantics. Do not render zero as measured activity when there is no KPI.

### Owner accounts

Keep the existing owner CRUD, enable/disable forms, and fields. Present it as a compact ledger with thin rules, small uppercase headings, and stacked fields on mobile. It remains admin-only.

### Actions

Primary actions use ink background/paper text; secondary actions use transparent paper/ink border; lime is reserved for active/positive emphasis and focus. Keep normal links and server-side permission behavior. Never bypass archive confirmation.

## Accessibility and state notes

- Keep semantic `main`, `aside`, `nav`, `header`, `section`, and table markup.
- Every icon-only control needs an accessible name.
- Never communicate state by color alone; pair color with text and/or icon.
- Keep `:focus-visible` at least 3px with lime and sufficient offset on both ink and paper.
- Use ink on lime for small text; do not use lime as small body copy on paper.
- Progress must expose `paid of expected` and percentage as text; native `<progress>` is acceptable when its value is accessible.
- Keep `role="alert"` for existing success/error alerts.
- Announce archived and read-only states in text, not opacity alone.
- Honor `prefers-reduced-motion`; no motion is required.
- Use tabular numerals and align money values. Never do arithmetic on formatted display strings.

## Synthetic vs real data mapping

| Prototype | Real implementation |
|---|---|
| `Al-Noor Academy` | `school.name`, `school_name()`, or `summary.campus.name`; never hard-code. |
| `$73,420` available net position | No current school-dashboard field; omit until a reviewed backend aggregate exists. |
| `+$8,460 net movement` | No current context; omit. |
| Overdue family balances | `kpi.arrears_cents` and `/campuses/{id}/arrears`; student detail belongs to arrears. |
| Uncategorised expenses | Do not imply this without backend data; use real expenses/report routes. |
| June close checklist | No current field; omit. |
| `79%` collection rate | `kpi.collected_percent`, paired with paid/expected. |
| `$61,100 expected` | `kpi.expected_cents`, scoped to the campus/period. |
| Record payment | `/campuses/{id}/payments`; preserve permissions. |
| Export month-end report | Existing `/campuses/{id}/reports` and CSV links; no new endpoint in this pass. |
| `AM` avatar | Existing `current_user()` user menu and role label. |

Money remains integer cents and is formatted by the existing `money()` global.

## File-by-file implementation plan

### `app/templates/school/dashboard.html`

Preserve imports, loops, role checks, route URLs, form actions, alerts, `has_reporting` branches, current data fields, and `money()` calls. Recompose markup into the premium intro, campus decision rows, progress, action cluster, and subordinate owner ledger. Add the stable `sf-*` hooks. Do not add prototype data or template arithmetic.

### `app/templates/base.html`

Only adjust shell classes/hooks needed for the premium rail, topbar, and canvas. Keep nav branches, permissions, mobile controls, user menu, scripts, footer, and confirmation dialog intact. No auth/role changes.

### `app/static/css/app.css`

Add a clearly delimited premium token/component section with the exact `--sf-*` tokens and transparency derivatives. Scope new rules under `.sf-dashboard` and shell hooks. Restyle rail, topbar, intro, campus rows, KPI values, rules, actions, progress, owner ledger, focus, and breakpoints. Avoid rewriting generated Tailwind output wholesale; leave unrelated pages available to their current system.

### `app/templates/components/ui.html`

Optional only if repeated markup warrants it: add a small premium KPI/decision-row macro with explicit parameters. Prefer dashboard-local markup first because campus actions and permission branches are specific. Do not change existing macro contracts without checking all call sites.

### `app/templates/components/icons.html`

No change expected. Reuse the existing building, arrow, eye, archive, user-plus, banknotes, warning, chart, and home icons.

### Backend/routes/services

No backend change is required for the first visual implementation. Graphify connects the dashboard to `SchoolDashboardService`, `CampusSummary`, `CampusKpi`, `schools/routes.py`, and `GET /campuses/{id}` (Community 109). Reporting and money truth connect through the reporting/integer-cents communities (2, 10, 34, 55, 72, 80, 84, 97, 111). Use those seams rather than recalculating values in Jinja.

Graphify also identifies `create_app()`, `authenticated_admin()`, `scope_context()`, and `require_scope()` as high-connectivity bridges. Do not bypass scope or permission paths from the template. A future true school-wide net position must come from a reviewed service/context contract with route/service tests.

## Verification checklist

- Superadmin: two active campuses, one archived campus, assigned/unassigned admins, reporting data.
- Owner/read-only: notice present, mutation controls absent, links correct.
- Reporting unavailable, no KPI, and no-campus states.
- All money uses `money()`; percentage uses `collected_percent`.
- Desktop/tablet/mobile widths; no primary KPI or action clipped.
- Keyboard-test sidebar, nav, campus links, archive confirmation, owner actions, and focus rings.
- Run existing dashboard/app smoke tests and available template/lint checks.
- Confirm only intended template/CSS files changed; no production behavior outside visual scope.

