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

**Status:** implemented

- [x] daisyUI compiles into the bundled app.css (Tailwind v4 `@plugin "daisyui"`); no CDN, works offline
- [x] App shell shows a grouped sidebar + topbar; top-only nav is gone; user name + role badge in the topbar
- [x] Sidebar collapses at narrower widths (down to ~1024px); nav groups match School/Finance/Reports/System
- [x] Inter font served from bundled woff2; Heroicons render via a reusable `icon(name)` macro
- [x] Shared components exist and are used by the re-skinned pages (no duplicated button/badge/table markup)
- [x] Toast + confirm-dialog + loading-spinner helpers work with HTMX (confirm dialog fires on an irreversible action like archiving or fee generation)
- [x] Login and setup wizard are the only pages without the sidebar
- [x] Semantic colors applied (green in / red arrears / amber partial) via badges, not color alone
- [x] Print CSS hides the app chrome; pages print cleanly
- [x] Route-level test asserts the shell renders the sidebar + logged-in user for authenticated routes (extends the existing `test_*_routes.py` pattern)

## Comments

Implemented on 2026-08-05 (commit `c3d75c7`). The design system lives in
`app/templates/components/`: `ui.html` (macros `page_header`, `card`, `btn`,
`badge`, `alert`, `stat_card`, `empty_state`, `table_scroll`, `form_field`,
`confirm_dialog`) and `icons.html` (`icon(name)` over inline Heroicons). The
shell is `base.html` — grouped sidebar (School · Finance · Reports · System)
that collapses to an overlay below 1024px, topbar with search slot + user menu
(role badge, log out), `toast-container`, and the shared confirm dialog. Tailwind
v4 + daisyUI 5.7.16 are compiled offline via `npm run build` in `assets-src` into
the committed `app/static/css/app.css`; Inter woff2 is bundled under
`app/static/fonts/`. HTMX helpers in `app/static/js/ui.js`: toasts
(success/error/warning, auto-dismiss), `data-confirm` dialog for irreversible
actions, `data-loading` button spinner (custom `.btn-loading` — daisyUI v5 has no
such class), sidebar toggle, and `data-password-toggle` (show/hide password on
login). Semantic colors follow UI-3 (green = money in, red = arrears/expenses,
amber = warnings; badges carry meaning, never color alone). Print CSS hides the
app chrome (`.no-print`) and white-washes the page. Every page built so far is
re-skinned onto the shell: login, setup, home, classes index/form/detail, class
badges, students search/edit/import/import_result, audit index, admin. Key bug
found in the browser: Tailwind v4 `-translate-x-full` sets the `translate`
property, so the sidebar open state must override `translate` (not `transform`).
Two Tailwind-v4 quirks: the sidebar collapse is `transition: translate …` plus a
`translate: 0` override, and the `icon` macro passes class strings through `{{ }}`
so they must stay literal. Route-level smoke tests added in `tests/test_app.py`
(`test_authenticated_pages_use_the_design_system_shell`,
`test_login_page_is_standalone_without_the_shell`); route test copy assertions
in `test_auth_routes.py`, `test_classes_routes.py`, and
`test_students_routes.py` were updated to match the reworded UI copy. Full suite
193 passed, mypy clean. Verification was hand-driven in a headless browser
(`chrome-devtools`): shell renders on every authenticated route, sidebar
collapses at ~900px, confirm dialog posts to the correct `/delete` endpoint
(`performAction` passes the clicked submitter through `form.requestSubmit`), and
the login show/hide toggle works. Later feature tickets (06–13) build on this
foundation; full receipt/statement print templates land with ticket 08.
