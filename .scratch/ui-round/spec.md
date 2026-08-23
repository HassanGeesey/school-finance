# UI round — Calm Slate SaaS re-skin

**Status:** ready-for-agent

Feature: `ui-round`. Applies `DESIGN.md` (Calm Slate SaaS design system) and the approved interactive prototype (`prototypes/school-finance-interactive.html`) to the whole app. Decisions: `project-decisions.md` → "Interactive prototype design session" (PROTO-1..3), "UI round planning session" (UIR-1..4). Terms: `CONTEXT.md`. ADR: `docs/adr/0003-school-campus-hierarchy.md` (campus owns branding and everything operational).

## Problem Statement

The multi-school tenant layer works, but its screens wear an ad-hoc look: Tailwind utilities assembled page by page plus one-off scoped stylesheets (the Private Office experiment). School-level and campus-level screens feel like different products. Numbers — the entire point of a finance app — are not consistently tabular or right-aligned. The approved prototype defines exactly what the product should look and behave like, but it lives as static HTML with simulated data; nothing in the real app follows it.

## Solution

Adopt Calm Slate SaaS app-wide: a token layer from `DESIGN.md` (slate canvas, slate-900 navigation rail, emerald/amber/rose/indigo functional accents, radii, shadows, Inter type scale) lands once in the shared stylesheet, every screen is rebuilt on shared components (buttons, badges, KPI cards, panels, ledger tables, progress bars, modal, toast), and the four prototype experiences become real screens driven by live data:

- **School Dashboard** — executive portfolio overview: 4-KPI row (collections vs expected %, net operating flow, outstanding arrears, operating campuses), then a Campus Financial Health deck with per-Campus collected/expenses/arrears stats and expected-vs-paid progress bars, drill-down into any Campus, archive affordance for the Superadmin, read-only badge treatment for Owners/Shareholders.
- **Campus operations view** — the drill-down: campus KPI strip (month collections with % of expected, expenses, outstanding balance, active enrollment) and the recent Month-tagged Payments ledger with receipt reprint.
- **Arrears queue** — per-Campus outstanding balances with overdue-month badges, urgency flags, guardian contact, and clear/settle actions.
- **Record Payment modal** — campus → student → amount → target Owed Month → method, with a live monospace receipt slip showing monthly rate, paid amount, partial-remaining status, and Credit rolled forward.

All other pages (classes, students, fee templates, waivers, expenses, reports, audit, settings, auth) are re-skinned with the same tokens and components. No backend, route, service, or schema changes; behavior is identical before and after.

## User Stories

1. As a Superadmin, I want the School Dashboard to show portfolio-wide KPIs in large tabular numerals, so that I can read the school's financial health at a glance.
2. As a Superadmin, I want a Campus card per branch with collected/expenses/arrears and an expected-vs-paid progress bar, so that I can compare branches instantly.
3. As a Superadmin, I want an obvious "enter campus" drill-down on each Campus card, so that I can go from portfolio view to one branch in one click.
4. As a Superadmin, I want campus provisioning and archive actions visible only to me on the School Dashboard, so that management controls never leak to other roles.
5. As a Superadmin, I want the navigation rail to always say who I am and what scope I'm in, so that I never lose my bearings between School and Campus contexts.
6. As a Superadmin, I want a campus selector in the topbar while drilling down, so that I can hop between branches without returning to the School Dashboard.
7. As an Owner/Shareholder, I want the same School Dashboard read-only with an explicit viewing badge, so that I can monitor the business without any risk of mutating it.
8. As an Owner/Shareholder, I want every mutation control replaced by explicit read-only notices (not merely hidden or faded), so that my view is honest about what I can do.
9. As an Owner/Shareholder, I want drill-down into each Campus's data presented read-only, so that I can investigate without changing anything.
10. As a Campus Admin, I want my operational pages restyled but behaving exactly as today, so that nothing about my job changes except how it looks.
11. As a Campus Admin, I want zero visibility of other Campuses preserved in the new UI, so that branch isolation survives the redesign.
12. As a Finance Officer, I want the payment flow as a compact modal with a live receipt preview, so that recording a payment takes seconds with zero ambiguity.
13. As a Finance Officer, I want the receipt slip to show partial-payment remaining and Credit rolled forward before I confirm, so that parents are told the truth at the counter.
14. As a Finance Officer, I want the arrears queue sorted into an actionable list with overdue months and urgency badges, so that follow-up calls take priority correctly.
15. As a Finance Officer, I want amounts right-aligned, bold, and tabular in every table, so that columns of money stay scannable and comparable.
16. As any campus user, I want badges (active, archived, urgent, month tags) rendered consistently as pills, so that status is recognizable at a glance anywhere in the app.
17. As any user, I want Esc to close modals and dialogs, so that I can back out of mistakes quickly.
18. As any user, I want the shell responsive (rail collapses on mobile, KPI grids stack 4→2→1), so that the app works on whatever screen I have.
19. As a parent receiving a printed receipt, I want the monospace receipt format kept with the campus profile addressing it, so that printed documents stay correct and branded.
20. As an auditor, I want the audit log restyled with the same ledger components, so that reviewing history feels like the rest of the product.
21. As a first-run user, I want the setup wizard and login pages wearing the same design system, so that the product feels finished from the first pixel.
22. As the .exe operator, I want the offline app functionally unchanged after the re-skin, so that single-machine schools lose nothing (visual refresh applies to both paths — one codebase).

## Implementation Decisions

- **Token layer:** all `DESIGN.md` front-matter tokens (colors, radii, shadows, spacing, type scale) land as CSS custom properties defined once in the shared stylesheet; components consume tokens only — no hardcoded hex outside the token block. The repo has no CSS build tooling (compiled Tailwind v4 artifact committed directly); the stylesheet stays hand-maintained in place.
- **Typography:** Inter (already self-hosted as woff2 400/600/700) with the DESIGN.md type scale; a `.num` utility (tabular numerals, tightened tracking) is mandatory on every amount, count, and percentage. Receipts stay monospace.
- **App shell:** fixed 240px slate-900 navigation rail (brand, grouped nav, role indicator footer) + 56px white topbar (breadcrumb, campus selector pill for school-scope users, search where it exists today, user pill with avatar) + workspace capped at 1280px with generous gutters. Mobile drops the rail behind the existing toggle/backdrop pattern.
- **Component set:** primary/secondary/emerald buttons (+ small variant), pill status badges (emerald/amber/slate + rose/indigo accents), KPI cards (label / big value / meta line), content panels (header/body), ledger tables (uppercase micro headers, hairline rows, hover, right-aligned bold tabular amount cells, `amount-head` right alignment), collection progress bar animated via `transform: scaleX` (never width), modal (backdrop blur, slide-in), toast.
- **Prototype-to-route mapping:** School Executive Dashboard → the School Dashboard route; Campus operations → the campus drill-down view (and the visual template for campus-staff home); Arrears queue → the unpaid-fees page; Record Payment modal → the existing record-payment flow re-plumbed as a modal with the live allocation slip. All data comes from existing routes/services — the prototype's simulated store and its floating view-switcher/role-toggle control bar are scaffolding and are not shipped.
- **Keyboard:** Esc closes modals/dialogs app-wide; the prototype's number-key view switching is adopted only if it does not fight existing shortcuts, guarded against firing while typing in inputs; the prototype's fake role-toggle key is dropped (roles come from auth).
- **No dead buttons (DEP-17 spirit):** prototype affordances whose backends don't exist (SMS/WhatsApp reminders, batch reminders, CSV export where no endpoint exists) are omitted, not stubbed.
- **Read-only honesty:** Owner/Shareholder and Superadmin-read-only surfaces use explicit badges and notices instead of opacity-hidden controls; permission gating logic itself is untouched (it already works and is tested).
- **No arithmetic in templates:** all derived figures (percentages, totals, net flow, credit rollover) keep being computed in services/route context; templates render values only (DESIGN.md Don't, existing rule respected).
- **Branding:** rail brand and receipts keep using the Campus profile name/logo/contact per ADR-0003; the prototype's static "Sunrise" branding is placeholder only.
- **Scope guard:** templates, stylesheet, and client JS only. Zero changes to routes, services, models, schema, tests' behavior contracts. The `.exe` shares this codebase, so it receives the visual refresh too; its functional model is untouched (UR-15 applies to function, not pixels — confirmed UIR-2/22).

## Testing Decisions

- **Single seam — HTTP routes** (existing TestClient pattern, prior art: `test_school_routes.py`, `test_*_routes.py`): assert external behavior, never classes/CSS/pixels.
  - An Owner/Shareholder GET of the School Dashboard and campus drill-down contains no mutating controls (no forms/buttons that POST); a Superadmin's does contain them.
  - Role-gated pages still render per role: campus staff never see the School Dashboard; cross-campus requests still return empty/404 (existing contract tests stay green untouched).
  - Every re-skinned route still returns 200 with its expected landmarks for authorized roles (smoke sweep across the page inventory).
  - Login/setup render unauthenticated; logout still posts.
- **Regression:** full existing suite stays green — the re-skin must change presentation only.
- **Visual fidelity is human-verified** against `prototypes/school-finance-interactive.html` in a browser (UIR-3) — side-by-side check of shell, dashboard, campus view, arrears queue, payment modal, and a sampling of re-skinned campus pages, desktop and narrow viewport.

## Out of Scope

- Any backend work: routes, services, models, schema, permissions logic, audit behavior.
- New features implied-but-absent in the prototype: messaging/reminders, exports without endpoints, notification center.
- Dark mode or additional themes; the system ships light-only.
- Print-layout redesign beyond keeping receipts correct and monospace under the new tokens.
- Postgres RLS and deployment-round follow-ups (already tracked elsewhere).
- Replacing the compiled-CSS approach with a build pipeline.

## Further Notes

- `DESIGN.md` is the normative token/component reference for every ticket in this feature; the prototype is the normative layout/interaction reference for the four mapped experiences.
- The Private Office experiment (master, `experiment(ui)` commit) is superseded; its scoped block comes out when the token layer lands.
- Glossary terms used as defined in `CONTEXT.md`: School, Campus, School Dashboard, Superadmin, Campus Admin, Finance Officer, Owner/Shareholder, Fee Template, Owed Month, Month-tagged Payment, Expected Amount, Waiver, Closed Month, Credit.
