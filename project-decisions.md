# School Finance Web App — Project Decisions

Grilling session log. Updated as decisions are made.

**Project:** School finance web app
**Stack:** Python + SQLite (FastAPI confirmed)
**Status:** Decisions in progress

---

## Decisions (so far)

| # | Question | Answer |
|---|----------|--------|
| Q1 | What is this project, really? | **A real system** — will actually run in a school (real money, real users) |
| Q2 | What does "school finance" cover for v1? | **Fee collection + Expenses + Arrears tracking** (budgeting, donations, payroll out of v1 scope) |
| Q3 | Who uses the system? | **Admin + Finance officer** roles (login + audit trail required; no view-only role for now) |
| Q4 | Where does it live? | **One machine** — office PC, SQLite single file, accessed via localhost |
| Q5 | Web framework | **FastAPI** |
| Q5b | Shipping | Must ship as an **.exe** easily (PyInstaller) — designed around this from the start |
| Q6 | UI architecture | **Server-rendered** — FastAPI + Jinja2 + HTMX + Tailwind + Chart.js. Bundled CSS/JS (works offline). One codebase → clean .exe packaging |
| Q7 | Billing unit | **Each student separately** (no family grouping) |
| Q8 | Fee structure | **Itemized structure** — fee items (Tuition, Boarding, Transport, Meals...), default per class/grade, editable per student. Term bill = sum of items |
| Q9 | Terms / school year | **Monthly billing, manual** — no terms calendar. Each month, the user clicks a button in the Finance module to generate that month's fees (itemized per student). Generation is manual, not automated |
| Q10 | "Fully modular" meaning | **Well-organized folders** (features in clean, layered folder structure) + **UI composed of reusable components** (reusable Jinja2 partials/macros). Not a plugin architecture |
| Q11 | Currency & locale | **USD**, UI in **English**. Payment methods kept simple — a basic method label (e.g. cash/bank/other), no complex integrations |
| Q12 | Payment methods | Answered in Q11 — kept simple (cash/bank/other label) |
| Q13 | Reports & receipts | **All**: Dashboard (charts), Income vs Expense, Arrears report, printable receipts per payment, expense-by-category. Receipts as printable HTML (no PDF engine) |
| Q13b | Additional reports (from Q21) | **Export students** (per class or all classes, CSV) · **Income report** · **Expense report** · **Paid students for a specific month** (and by extension unpaid) · **Summarized finance report**. Every report also has **Export CSV** |
| Q14 | Data import | **Class-first import** — user creates a Class, opens it, then imports CSV students *into that class* (or adds manually). No class-name matching needed; CSV holds student fields only. Imported students inherit the class's fee structure |
| Q15 | Backups | **Automatic on startup + manual "Backup now" button** — SQLite copied to `backups/` folder, keep ~30 copies |
| Q16 | Audit trail | **Yes, full audit log** — every payment, expense, fee generation, and edit logged (who/when/what changed). Admin can browse. No hard deletes — archive instead |
| Q17 | Monthly fee generation | **Choose: Class (or All classes) + Month + Year, then Generate.** Creates one monthly charge per student = sum of their class's fee items. **Duplicate-safe** per class+month+year (refuses double generation). Admin-only per-student adjustments afterwards (extras/waivers) |
| Q18 | Payments | **Partial payments allowed.** Payment reduces **oldest unpaid charges first** (auto, no month-picking). Overpayment becomes **credit** on the student account (no refunds in v1). Receipt printed right after each payment |
| Q19 | Expenses | **Admin-managed category list** (Salaries, Utilities, Supplies, Maintenance, Transport, Other). Expense record = date, category, description, amount, payment method. **No attachments in v1** |
| Q20 | Lifecycle | **No hard deletes.** Students: active → inactive (archived), history + arrears stay. Classes have status: **Active / Completed / Inactive** — Completed stops generating fees but keeps records and tracks outstanding arrears |
| Q21 | CSV export | **Every report has Export CSV** (arrears, income, expense, students, expenses-by-category, summarized finance) |
| Q13b | Additional reports | **Export students** (per class or all classes) · **Income report** · **Expense report** · **Paid students for a specific month** (and unpaid) · **Summarized finance report** |
| Q22 | First run | **Setup wizard** on first launch — create the Admin account (name, username, password) before login is possible. No default passwords |
| Q23 | .exe runtime | **Hidden process + system tray icon** (Open app / Quit). Server runs on `localhost`, browser opens automatically. Closing the tab does NOT stop the app — quitting via tray does. One instance only |
| Q24 | Role permissions | **Admin**: everything + manage users/classes/fee items, per-student adjustments, expense categories, audit log, backup/restore, shutdown. **Finance officer**: record payments & expenses, generate monthly fees, run reports/exports, print receipts. No config access |

---

## UI decisions (UI grilling session)

| # | Question | Answer |
|---|----------|--------|
| UI-1 | Overall look & feel | **Clean modern dashboard** — light theme, sidebar + topbar, cards, subtle shadows, generous spacing |
| UI-2 | Navigation layout | **Grouped sidebar + topbar** — groups: School (Classes, Students), Finance (Fees, Payments, Expenses), Reports, System (Audit, Settings). Sidebar collapsible |
| UI-3 | Colors | **Modern, professional, user-friendly.** Teal/emerald primary. Semantic: green = money in/paid, red = arrears/expenses/overdue, amber = partial/warnings, slate = neutral. Badges/chips carry meaning |
| UI-4 | Component library | **daisyUI + Tailwind**, components wrapped as reusable Jinja2 partials/macros. Bundled offline |
| UI-5 | Feedback & interactions | Toasts (success/error/warning, auto-dismiss), confirm dialogs for irreversible actions, inline loading states, friendly empty states |
| UI-6 | Fonts & icons | **Inter bundled** locally (woff2, system fallback) + **Heroicons inline SVG** |
| UI-7 | Dashboard | KPI stat cards (collections, arrears, expenses, net), recent activity list, quick actions (Record payment · Generate fees · Record expense · Add student). **Charts deferred — revisit** |
| UI-8 | Fee generation screen | Single card: Class/All + Month + Year + Generate. Confirm dialog with **per-class breakdown** (class → students → total). Success toast + summary. Red alert on duplicates |
| UI-9 | Record payment screen | Search student (live balance) → amount + method → live confirmation line → Save → toast + Print receipt. Nudges on overdue |
| UI-10 | Student account page | Header (name/class/status + big color-coded balance), expandable charges with item breakdown + adjustments, payments list, balance footer, actions (record payment, adjust month, print statement) |
| UI-11 | Class page | Header (name, status badge, fee summary), action bar (Add student · Import CSV · Generate fees · Edit structure), students table **with paid/unpaid/all filter** |
| UI-12 | Reports pages | One reusable report template: filter bar, summary line, table, Export CSV. Arrears age color-coded (amber >30d, red >60d) |
| UI-13 | Print | Print CSS hides app chrome; print-ready **receipt** (school name, receipt no., student, amount, method, date, signature) and **statement** templates |
| UI-14 | Login & setup wizard | Minimal centered login card (show/hide password, error banner) + 3-step setup wizard (Welcome → Admin account → All set). Only pages without sidebar |
| UI-15 | Devices & accessibility | **Desktop-first**, adapts down to ~1024px (sidebar collapses). Mobile out of scope. Accessibility: keyboard-navigable, focus rings, color never sole signal |

---

## Requirements summary

**Project:** School finance web app — real system for a real school, one office PC, USD, English.

**Stack:** Python + FastAPI + SQLite, server-rendered (Jinja2 + HTMX + Tailwind + Chart.js), bundled assets (offline), packaged as a single hidden .exe with tray icon.

**Architecture:** Well-organized feature folders (auth, students, classes, fees, payments, expenses, arrears, reports) + reusable UI components (Jinja2 partials/macros). Shared layer underneath (DB, config, base layout).

**Modules (v1):** Fee collection, Expenses, Arrears tracking.

**Users:** Admin + Finance officer. Login required. Setup wizard on first run. Full audit log.

**Core flow:**
1. Admin creates Classes (status: Active/Completed/Inactive) and sets itemized fee structures per class.
2. Inside a class, students added manually or imported via CSV. No hard deletes — students archive to inactive.
3. Monthly (manual): user picks Class/All + Month + Year → Generate. Duplicate-safe. One charge per student = sum of class fee items. Admin can adjust (extras/waivers).
4. Parents pay partial amounts — payment clears oldest unpaid charges first. Overpayment becomes credit. Receipt printed after each payment. Payments have simple method label (cash/bank/other).
5. Finance records expenses against admin-managed categories (date, category, description, amount, method).
6. Reports (all with CSV export + dashboard charts): Income vs Expense, Arrears, Expense-by-category, Paid students per month, Summarized finance, student lists. Printable HTML receipts.

**Operational:** Backup automatically on startup + manual button (keep ~30). One instance. Localhost server, browser opens automatically, quit via tray icon.

---

## Settings / branding grilling session

| # | Question | Answer |
|---|----------|--------|
| S-1 | "System name" = which name? (product name vs school name) | **The school name** — configurable, shown on receipts, sidebar brand, tab title, footer. Product name "School Finance" stays fixed as the software's label (setup wizard, Settings context) |
| S-2 | Where does the school name surface? | **Everywhere currently branded** — sidebar brand block, tab title, footer, printed receipts. Setup wizard + login keep "School Finance" (they're about the software). Reports keep their own page headers |
| S-3 | What fields make up "contact info"? | **Address** (multi-line), **Phone**, and a field for **email or website** — all optional free text |
| S-4 | Validation on contact fields? | **No validation** — all four fields are plain strings (Address, Phone, Email, Website). Blank fields simply don't display |
| S-5 | Logo: format, storage, placement | **Any image format accepted** (no strict size limit). Stored as a file next to the data (e.g. `data/logo.<ext>`); DB stores the filename. Shows in the sidebar brand block + top of printed receipts. No-logo fallback = current `banknotes` icon / nothing. "Remove logo" option available. **UI:** logo/name kept **centred** in their container with **padding to avoid overflow** |
| S-6 | Where do the profile settings live? | **Single-row `school_profile` DB table** — typed columns (school_name, logo_filename, address, phone, email, website), fits the existing SQLAlchemy + create_all + audit pattern |
| S-7 | First launch | **Setup wizard gains a required "School name" field** (alongside name/username/password). Logo + contact optional, configured later in Settings |
| S-8 | Audit trail | **Yes — profile edits and logo uploads/removals are audited** (who changed what), consistent with backups and user management |
| S-9 | Historical receipts | **Current profile, rendered at print time** — old receipts reprinted later show the then-current school details (no per-receipt snapshotting) |
| S-10 | Empty school name edge case | **School name is always required** — the Settings form refuses an empty value (same as the setup wizard), so the brand can never go blank |
| S-11 | Scope of the profile on printed documents | **Applies to printed statements too** — receipts *and* the student statement both show the current school name, logo, and contact block |

---

## Student list filters grilling session

| # | Question | Answer |
|---|----------|--------|
| SLF-1 | Which student list gets the paid/unpaid + class filters? | **The `/students` page** (school-wide search page). Class page already scoped to one class, so a class filter there would be meaningless |
| SLF-2 | How is paid/unpaid determined? | **Per selected month** (month+year picker, defaults to current month) — same basis as the paid-students report |
| SLF-3 | Partially-paid status? | **Three-way + All** — filter options are All / Paid / Partial / Unpaid (partial is its own state, matching the domain) |
| SLF-4 | Students never billed in the selected month | **Excluded from the Paid/Partial/Unpaid filters** (they don't owe, so "unpaid" would be wrong); they still appear under All |
| SLF-5 | Archived students in filtered results | **Included** — their history and arrears persist, so paid status still matters; the existing status badge already marks them archived |
| SLF-6 | What the results show | **A new "Paid" column** — the selected month's paid/partial/unpaid badge plus the remaining amount (e.g. "Unpaid — $45.00"), rendered for the selected month |
| SLF-7 | How the month is chosen | **Dropdown of billed months only** (same as the reports), defaulting to the most recent billed month; no paid column/status filter when no month has been billed |
| SLF-8 | Delivery | Confirmed plan (form params `q`/`period`/`class_id`/`status`; paid logic reuses `ReportService.paid_students`; `StudentService.search_students(q, class_id=None)`; defaults: most recent billed month, All status, All classes) → split into tickets and implement |

---

## Dockploy deployment grilling session

| # | Question | Answer |
|---|----------|--------|
| D-1 | What does this deployment change? (replaces the .exe or coexists?) | **Coexists — single branch.** User floated "two branches" (one per delivery path); grilled down. Verdict: one `main` branch, both delivery paths live side by side — `packaging/` for the .exe, new `docker/` folder for the container. Docker changes are purely additive (Dockerfile, .dockerignore, compose), `app/` needs zero rewrite (data dir already env-driven, sessions already DB-backed). Branching would fork 100% shared code and force cherry-picking every fix twice |
| D-2 | Where does Dockploy run? | **Public VPS with a domain** (recommended, accepted). App reachable over the internet, HTTPS via Dockploy/Traefik Let's Encrypt, server-grade auth already in place |
| D-3 | Domain | Subdomain of an existing domain (recommended, accepted) |
| D-4 | Actual domain | Base domain **hgeesey.store** owned by user. Confirmed app domain: **ict.hgeesey.store** |
| D-5 | Deployment method | **Docker Compose in Dokploy** (user chose; researched). Compose service joins external `dokploy-network`, `restart: always`, no `container_name`; domain via Dokploy Domains tab (Traefik/Let's Encrypt automatic). Still requires a `Dockerfile` — compose `build:` needs it |
| D-6 | Compose file location | **Repo root** (`docker-compose.yml`), Compose Path set in Dokploy UI (recommended, accepted). Domain/secrets stay out of git via env overrides in the UI |
| D-7 | Data persistence & backups | **Named volume `school-finance-data` → `/data`**, `SCHOOL_FINANCE_DATA=/data`. Keep app-level backups (startup + manual → `data/backups/` in the volume) **and** enable Dokploy scheduled volume backup (server disk) as second layer (recommended, accepted) |
| D-8 | Existing data | **Fresh deployment** — no live data, empty volume, setup wizard on first visit. No migration tooling; note the manual DB-file-copy step in deploy docs for later |
| D-9 | Workers | **Single uvicorn process, no `--workers`** (SQLite single-file constraint; traffic is small) (recommended, accepted) |
| D-10 | In-app "Shut down" button in Docker | **Disabled via env flag** (`SCHOOL_FINANCE_DISABLE_SHUTDOWN=1` → button hidden + route refused). ~10-line change in `app/system`; `.exe` path unaffected (env unset) (recommended, accepted) |
| D-11 | Secure session cookie over HTTPS | **Set `Secure` flag when `request.is_secure`** (Traefik forwards `X-Forwarded-Proto`); localhost HTTP unaffected (recommended, accepted) |
| D-12 | Brute-force login protection | **Out of scope now** (recommended, accepted) — PBKDF2-600k is the existing deterrent; note as a follow-up feature in deploy docs |

## UI redesign grilling session

| # | Question | Answer |
|---|----------|--------|
| R-1 | Who primarily uses the app day-to-day? | **School admin/secretary at one desk** — one person on the school's machine runs the whole finance flow (setup, fees, payments, expenses, arrears) |
| R-2 | What does "simple, structured, easy to navigate" mean for this redesign? | **Reskin the existing structure** — keep the pages, routes, and navigation groups as-is; make the visual design cleaner, calmer, and more consistent |
| R-3 | Binding visual constraints? | **Must stay light and professional** (it's school money data). No school-color or other brand commitments beyond the configurable name/logo |
| R-4 | How to decide the direction? | **Prototype first** — user asked to see the design as a working prototype before committing to a direction |
| R-5 | Workflow preference | **Prototype every time** — for every design change going forward, show a working prototype in the browser before building it for real |
| R-6 | Chosen direction | **Office Noticeboard** — warm paper-white boards with hairline edges, pin tabs, grouped "board index" sidebar, school-ink blue accent, semantic green/amber/red only for money status. Full-screen prototype of the key screens approved next |
| R-7 | Dashboard charts | **Real charts, not hand-drawn mockups** — use the app's own Chart.js: income-vs-expenses bar+line combo, arrears-by-age doughnut, expenses-by-category horizontal bar, plus a Recent expenses board |
| R-8 | Accent color | User disliked the first navy-on-paper default. Prototype got a **live palette switcher** (accent Teal/Navy/Forest × ground Paper/Cool). **Final pick: Navy accent on Cool ground** — the user's favourite, now the prototype default |
| R-9 | Page layout approval | User reviewed the live reskin and **approved the layout across pages** (Payments, Expenses, and the rest of the app) — the board/noticeboard structure stays as built |

---

## Fee workflow grilling session (late-enrolled students)

> **Governing goal (user):** make the system **as simple and useful as possible**. Every remaining decision is judged against this — when in doubt, choose the option with the least machinery that still does the job.

| # | Question | Answer |
|---|----------|--------|
| FW-1 | Confirm the failing scenario | **Yes.** Class fee generated for a month, then a new student added to the class after generation → the student gets **no charge for that month**, so their balance reads $0 and they never appear in "who didn't pay this month". How it's patched today: user did not specify (no answer beyond confirming the hole) |
| FW-2 | Assessed: "just record payments per month, filter paid/not-paid by month" | **Right:** kills the generation step entirely (no hole, no duplicate-safety), "who didn't pay" falls straight out, one source of money-in truth. **Wrong:** (1) "expected amount" is undefined — only "paid anything?" is answerable, not "paid the right amount"; (2) no frozen history — a fee-structure change retroactively redefines past months (violates snapshot principle); (3) per-student extras/waivers still need a per-student+month slot = a charge in all but name; (4) payments are untethered — partials/credits need a month to attach to, re-importing the per-month obligation it tried to remove. Industry systems keep the invoice/charge and instead **auto-bill on enrollment**. Model choice still pending |
| FW-3 | Proposed alternative to the "wrongs": fee types + enrollment assignment | **Student-fee-plan pattern (matches OpenEduCat).** Named **fee types** (e.g. Standard/Boarding), each with an amount; a student is **assigned a fee at enrollment** and that fixed amount is what they owe per month; payments recorded against it; "not paid" = no (full) payment for the month. Note: a per-student fixed monthly amount **is a charge** — just created once at enrollment instead of monthly. Still open: frozen-vs-live amount, fee-type shape, mid-month proration, extras/waivers storage, payment month-tagging |
| FW-4 | How do we make enrollment just bill the student? (direction) | **Bill from enrollment.** Being enrolled *is* the billing — a student's monthly obligation derives from being an active member of a class with a fee structure, for every month they're enrolled. **No Generate button, no generation records, no duplicate-safety.** Enrollment auto-creates charges for the current month (and back months per policy). The hole disappears by construction: you cannot enroll without being charged |
| FW-5 | User's counter-proposal while answering the enrollment-date question | **Simplified model — no charge rows at all.** When a student is created, the clerk enters **how much they should pay** (a monthly amount on the student record). Recording a payment = pick **student + month + amount paid**; the system **compares should-pay vs paid** for that month. This is FW-2's "record payments only" made viable by adding the expected amount (FW-2's missing piece). **Supersedes FW-4's charge-row assumption.** Still open: live-vs-frozen monthly amount, fee-edit retroactivity, partial/overpayment handling, payment month-tagging, arrears derivation, what happens to existing Charge/GenerationRecord data |
| FW-6 | Is the "how much they should pay" amount a single live number or frozen per month? | **Single amount, but effective-dated (partially superseded by FW-20).** Originally: one number on the student, fee edits retroactively recompute past months (accepted as a simplification). After the shortcomings review, the retroactive part was replaced: amount changes take effect **from a chosen month onward** (FW-20), so past months are frozen. "One student pays less" = a lower amount (effective-dated or a cheaper template) |
| FW-7 | What is a fee template? | **A named monthly amount** — name + one amount (e.g. "Standard — $100"). Created once; adding a student assigns a template or a custom amount. Each class carries a **default template** (bulk-add convenience); every student can override to any template or custom amount. No itemized bundles — receipts show the amount paid, and the comparison only needs the total |
| FW-8 | A student enrolls mid-month — what do they owe for that first month? | **Prorate the first month by days** (user's call, over the recommended full-month rule). Implies the student carries an actual **enrollment date**, not just a start month. Exact formula still to be pinned (FW-9); proration is intended for the first month only |
| FW-9 | Exact proration formula | **First month only** is prorated; every month after is full. `should-pay = template amount × (days from enrolled_on through end of that month, inclusive) ÷ (days in that month)`, rounded to the nearest cent. Enroll 20 Mar, $100/mo → 12/31 → $38.71. Enroll on the 1st → full month. Enrollment date is day-precise (`enrolled_on`, defaults to today, editable). **SUPERSEDED by FW-10 — proration abandoned** |
| FW-10 | User's revision: proration → full first month + waive charge | **Drop proration entirely.** The first month bills the **full** template amount like any other month. Forgiveness becomes a **"waive charge"** feature: a per-(student, month) waiver that reduces (or zeroes) that month's expected amount, with a label/reason. The tiny mid-month partial is simply waived in full if it's not worth collecting. Waivers are the only per-month record in the otherwise charge-less model. Semantics still being pinned (who may waive, scope, reason required) |
| FW-11 | Exact "waive charge" spec | **Accepted.** A waiver targets one student + one month (any month). It reduces that month's expected amount by a given amount; expected never goes below zero. Multiple waivers can stack on the same month. A reason/label is required. Comparison per month: `expected = student's monthly amount − total waivers (min 0)`, then paid vs expected. Waiving a month in full effectively starts billing the following month. Replaces the earlier "first billed month" toggle. **Extras still open (FW-12)** |
| FW-12 | Do we also need "extras" (one-off charges on a month)? | **Waivers only.** No extra-charge records. One per-month record kind only |
| FW-13 | Who can waive a charge? | **Both Admin and Finance officer** can waive (over the recommended Admin-only). The audit log records who and why |
| FW-14 | Which months does a student owe, and when do they stop? (researched against professional systems) | **Start at the month of `enrolled_on`; owe through the full month in which they're archived; stop after it.** Every month in between while active is compared: `expected − waivers − paid`. Professional convention confirmed: explicit enrollment date (never the data-entry date), first period billed full (anniversary billing, Jackrabbit's configurable no-prorate), and service-through-period-end on leaving (full leaving month, no prorated refund). Requires capturing `archived_on` when archiving |
| FW-15 | A parent pays more than a month's expected — what happens to the excess? | **Roll-forward credit.** The excess reduces the next owed month(s): March overpaid by $20 → April's expected becomes $80. Matches the old `Credit` concept; paying ahead works naturally. The per-month figure ("paid toward this month") and the account balance (total expected − total paid − waivers) are now distinct numbers |
| FW-16 | When recording a payment, which months can be picked? | **All months.** Not limited to the enrolled range — months may be skipped (school holidays/closure), so the clerk needs to tag payments to any month. Led to the closed-month question (FW-17) |
| FW-17 | How does the system know a month is skipped (school holiday/closure)? | **School-wide closed months.** The admin maintains a simple "closed months" list (e.g. in Settings). Closed months are excluded from everyone's owed range automatically — no expected amount, no "unpaid" flag, they simply don't appear. A payment tagged to a closed month just becomes credit. Correct reports by construction, one click per closed month |
| FW-18 | Is there real data on the live site that would need migrating? | **Nothing real yet.** Local DB empty, live deployment ~3 days old from an empty volume with only test data. The model change is a **clean schema reshape** — no migration. Students, classes, users, expenses, payments survive; the billing machinery (charges, adjustments, generation records, fee items, payment allocations) is simply replaced |
| FW-19 | When a fee template's amount changes, do existing students follow? | **Linked, effective-dated.** A student assigned to a template stays linked; raising the template's amount (from a chosen month) propagates to every linked student from that month. Students with a custom amount or another template are untouched. Past months keep their amount in force |
| FW-20 | Shortcomings fix: amount changes must not rewrite history | **Effective-dated amounts.** An amount change (per-student or template) carries an **effective month** (default: next month); a month's expected uses the amount in force for that month. Past months are frozen — "Paid for March" can never change because of a July fee raise. Implemented as a small per-student amount-change record, not a billing engine. This supersedes FW-6's retroactive recompute and FW-19's immediate propagation |
| FW-21 | Shortcomings fix: credit roll-forward order | **Oldest owed month first, visibly.** Carried credit covers shortfalls on the oldest owed months before later ones, until exhausted; the account shows how much credit each month consumed. A student's status is computed: payments tagged to the month first, then carried credit to the oldest shortfalls |
| FW-22 | Shortcomings guardrails: payment recording | **(1)** When recording a payment, the oldest unpaid month is shown first for the clerk to tag — never silently defaulted to "this month". **(2)** Warn (don't block) when the tagged month is outside the student's owed range (e.g. a fat-fingered future month) |

## Deployment outcome (live)

- **Live at https://ict.hgeesey.store** — deployed 2026-08-07 via Dokploy compose service `school-finance` (project `school-finance`, production env), built from `HassanGeesey/school-finance` branch `master` at commit `09e284c`.
- Docker Compose build from repo root `docker-compose.yml`; container `schoolfinance-sokmd6-school-finance-1` running, volume `school-finance-data` → `/data`, `SCHOOL_FINANCE_DATA=/data`, `SCHOOL_FINANCE_DISABLE_SHUTDOWN=1`.
- Domain `ict.hgeesey.store` → port 8000, HTTPS + Let's Encrypt (DNS validated); Traefik route live.
- Setup wizard confirmed at `/setup` (fresh install, volume empty).
- Not yet verified post-setup: admin account creation, `Secure` cookie on login, shutdown card hidden, volume backup schedule.
