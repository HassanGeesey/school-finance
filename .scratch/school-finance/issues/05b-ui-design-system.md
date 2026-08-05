# 05b — UI design system & app shell

**What to build:** The full design system from the UI grilling decisions (UI-1..UI-15, in the spec's "UI Design" section), plus re-skinning the pages built so far onto it. This is the single foundation every later feature ticket builds on. Presentation work — verified by hand in the browser, plus a route-level smoke test (no service-seam TDD here; the UI is outside that seam by design).

Delivers:
- daisyUI wired into the Tailwind v4 build, compiled offline into the bundled `app.css`
- Grouped sidebar (School · Finance · Reports · System) + topbar with user menu and role badge, replacing the current top-only nav
- Inter font bundled (woff2) with system fallback; Heroicons as inline-SVG Jinja macro (`icon(name)`)
- Semantic colors: emerald primary; green/red/amber money semantics; badges carry meaning
- Reusable Jinja2 components/partials: button, card, stat-card, table, badge, modal, toast, form-field, empty-state
- HTMX helpers: toast trigger (success/error/warning, auto-dismiss), confirm dialog, loading spinner on buttons
- Existing pages re-skinned: login, setup, home, admin, audit index, classes index/detail/form
- Print CSS groundwork (full receipt/statement templates land with ticket 08)

**Blocked by:** 05 — Students

**Status:** ready-for-agent

- [ ] daisyUI compiles into the bundled app.css (Tailwind v4 `@plugin "daisyui"`); no CDN, works offline
- [ ] App shell shows a grouped sidebar + topbar; top-only nav is gone; user name + role badge in the topbar
- [ ] Sidebar collapses at narrower widths (down to ~1024px); nav groups match School/Finance/Reports/System
- [ ] Inter font served from bundled woff2; Heroicons render via a reusable `icon(name)` macro
- [ ] Shared components exist and are used by the re-skinned pages (no duplicated button/badge/table markup)
- [ ] Toast + confirm-dialog + loading-spinner helpers work with HTMX (confirm dialog fires on an irreversible action like archiving or fee generation)
- [ ] Login and setup wizard are the only pages without the sidebar
- [ ] Semantic colors applied (green in / red arrears / amber partial) via badges, not color alone
- [ ] Print CSS hides the app chrome; pages print cleanly
- [ ] Route-level test asserts the shell renders the sidebar + logged-in user for authenticated routes (extends the existing `test_*_routes.py` pattern)
