# 01 — Token layer, component set, app shell

**What to build:** Calm Slate SaaS becomes the app's single visual language. DESIGN.md's front-matter tokens land once as CSS custom properties (colors, radii, shadows, spacing, Inter type scale); the shared component vocabulary is built from them (primary/secondary/emerald buttons + small variant; emerald/amber/slate/rose/indigo pill badges; KPI cards; content panels; ledger tables with uppercase micro headers and right-aligned bold tabular amount cells; collection progress bar animated via `transform: scaleX`; modal with blurred backdrop and slide-in; toast). The app shell is rebuilt: fixed 240px slate-900 navigation rail (brand, grouped nav, role indicator footer), 56px white topbar (breadcrumb, campus selector pill for school-scope users, user pill with avatar), workspace capped at 1280px with generous gutters, mobile collapsing the rail behind the toggle/backdrop pattern. The superseded Private Office scoped styles come out. Auth screens (login, setup wizard) are re-skinned as this ticket's end-to-end proof slice. No route, service, or template behavior changes beyond markup/classes.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Every hex value lives in the token block; components consume tokens only
- [ ] `.num` utility (tabular numerals) exists and is applied to amounts/counts/percentages in touched templates
- [ ] Rail shows correct nav groups and role indicator for Superadmin, Owner/Shareholder, Campus Admin, Finance Officer; mobile rail toggle works
- [ ] Topbar breadcrumb, campus pill (school-scope users only), and user menu render for each role
- [ ] Login and setup wizard wear the new system unauthenticated
- [ ] Private Office experiment styles removed; no page regresses functionally
- [ ] Full test suite stays green

## Comments

-
