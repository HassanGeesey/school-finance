# 01 — Token layer, component set, app shell

**What to build:** Calm Slate SaaS becomes the app's single visual language. DESIGN.md's front-matter tokens land once as CSS custom properties (colors, radii, shadows, spacing, Inter type scale); the shared component vocabulary is built from them (primary/secondary/emerald buttons + small variant; emerald/amber/slate/rose/indigo pill badges; KPI cards; content panels; ledger tables with uppercase micro headers and right-aligned bold tabular amount cells; collection progress bar animated via `transform: scaleX`; modal with blurred backdrop and slide-in; toast). The app shell is rebuilt: fixed 240px slate-900 navigation rail (brand, grouped nav, role indicator footer), 56px white topbar (breadcrumb, campus selector pill for school-scope users, user pill with avatar), workspace capped at 1280px with generous gutters, mobile collapsing the rail behind the toggle/backdrop pattern. The superseded Private Office scoped styles come out. Auth screens (login, setup wizard) are re-skinned as this ticket's end-to-end proof slice. No route, service, or template behavior changes beyond markup/classes.

**Blocked by:** None — can start immediately.

**Status:** implemented

- [x] Every hex value lives in the token block; components consume tokens only
- [x] `.num` utility (tabular numerals) exists and is applied to amounts/counts/percentages in touched templates
- [x] Rail shows correct nav groups and role indicator for Superadmin, Owner/Shareholder, Campus Admin, Finance Officer; mobile rail toggle works
- [x] Topbar breadcrumb, campus pill (school-scope users only), and user menu render for each role
- [x] Login and setup wizard wear the new system unauthenticated
- [x] Private Office experiment styles removed; no page regresses functionally
- [ ] Full test suite stays green *(round-level gate — run at sign-off, ticket 08)*

## Comments

Built: DESIGN.md front-matter landed as `--sf-*` CSS custom properties once in the hand-maintained layer of app.css (all 36 hex lines verified inside the token block; legacy daisyUI theme vars remapped onto tokens so not-yet-re-skinned pages inherit the language). Component vocabulary shipped: primary/secondary/emerald buttons + small variant, five-color pill badges, KPI cards, panels, ledger tables (uppercase micro headers, hairline rows, right-aligned bold tabular amounts + amount-head), progress bar animated via transform:scaleX, dialog-based modal with blurred backdrop + slide-in, toast. base.html shell rebuilt: 240px slate-900 rail with grouped nav and role-indicator footer (`role_label`), 56px topbar with School→Campus breadcrumbs, campus pill for school-scope users only, user pill; workspace capped at 1280px; mobile keeps existing toggle/backdrop pattern. ui.js now offers declarative data-modal-open/data-modal-close wiring with Esc handling guarded against input focus — later tickets need zero JS for modals. Auth login/setup re-skinned unauthenticated as proof slice. Superseded notebook/Private Office scoped styles removed.

Verification: targeted suites green with tests untouched — test_auth_routes + test_app + test_school_routes + test_admin_routes + test_tenant_scope + test_fee_money_scope = 94 passed. Full-suite regression gate deferred to round sign-off per ticket 08.

Commit: `fb1e9e4`
