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
