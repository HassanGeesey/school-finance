# School Finance App — Spec

Status: ready-for-agent
Feature: school-finance

## Problem Statement

A real school currently tracks student fees, expenses, and arrears by hand (ledgers and spreadsheets). Money goes in and out across many students and many months, and the office needs a single trustworthy record of who has paid, who still owes, and what the school has spent — without double-charging students, losing receipts, or being unable to prove what happened when.

The system runs on one office PC, is used by a small staff (an Admin and a Finance officer), and must be dependable: every transaction logged, no data ever hard-deleted, and easy to back up.

## Solution

A single-machine web app: Python + FastAPI + SQLite, server-rendered UI (Jinja2 + HTMX + Tailwind + Chart.js), packaged as a hidden Windows .exe with a system-tray icon. The office opens the app in a browser; the app keeps the books.

The core flow:

1. Admin creates **Classes** (status Active/Completed/Inactive) and sets each class's **fee structure** (itemized items like Tuition, Boarding, Transport, Meals, each with a monthly price).
2. Students are added manually or **imported via CSV inside a class**; they inherit the class fee structure.
3. Each month (manual, button-triggered): pick Class/All + Month + Year → **Generate**. Creates one monthly charge per student = sum of their fee items. Duplicate-safe: a class+month+year can only be generated once. Admin can adjust individual students afterwards (extras/waivers).
4. Parents pay **partial amounts**; a payment clears the **oldest unpaid charges first**; overpayment becomes **credit**; a printable **receipt** is produced after every payment.
5. Finance records **expenses** against an **Admin-managed category list** (date, category, description, amount, method).
6. Reports: Dashboard with charts, Income vs Expense, Arrears, Expense-by-category, Paid students per month, Summarized finance report, student lists — all with **CSV export**. Receipts are printable HTML.
7. **Full audit log** of every action; automatic + manual **backups**; no hard deletes.

## User Stories

1. As a new Admin, I want a setup wizard on first launch, so that I can create my admin account before anyone logs in.
2. As a user, I want to log in with a username and password, so that only authorized staff can access the books.
3. As a user, I want my role (Admin / Finance officer) to determine what I can do, so that Finance can run daily operations but only Admin changes configuration.
4. As an Admin, I want to create Classes, so that I can group students and assign fee structures.
5. As an Admin, I want to edit a Class's fee structure (add/remove/price fee items), so that each grade's monthly fee reflects the school's charges.
6. As an Admin, I want to mark a Class Completed or Inactive, so that ended/paused classes stop generating fees while keeping their records.
7. As a user, I want to open a Class and add students manually, so that I can register new students.
8. As a user, I want to import students into a Class from a CSV, so that I don't have to hand-type an existing register.
9. As a user, I want imported/added students to inherit the Class fee structure, so that fee generation works without extra setup.
10. As a user, I want to archive a student (mark inactive) without deleting them, so that history and outstanding arrears stay intact.
11. As a Finance officer, I want to generate monthly fees for a chosen Class (or All classes) for a chosen Month and Year, so that each student gets a correct monthly charge.
12. As a Finance officer, I want fee generation to be duplicate-safe, so that double-clicks or accidental re-runs never double-charge students.
13. As an Admin, I want to adjust an individual student's month (add an extra fee item or apply a waiver/discount), so that exceptions are handled without corrupting the structure.
14. As a Finance officer, I want to record a partial payment against a student, so that parents can pay in installments.
15. As a Finance officer, I want a payment to clear the oldest unpaid charges first, so that arrears are reduced correctly and automatically.
16. As a user, I want overpayments to become a credit on the student's account, so that balances stay honest without needing refunds.
17. As a Finance officer, I want to record the payment method (cash/bank/other), so that the office can reconcile money received.
18. As a Finance officer, I want a printable receipt produced for each payment, so that parents get proof of payment.
19. As a user, I want to see a student's account: charges, payments, credits, and current balance, so that I can answer "how much is owed?" instantly.
20. As a user, I want to see which students have arrears and how old the debt is, so that the office can chase unpaid fees.
21. As a Finance officer, I want to record an expense against an existing category, so that spending is tracked.
22. As an Admin, I want to manage the expense category list, so that categories reflect how the school classifies spending.
23. As a user, I want a Dashboard with charts (collections, arrears, expenses), so that I can see the financial picture at a glance.
24. As a user, I want an Income vs Expense report for any month, so that I can judge monthly performance.
25. As a user, I want an Arrears report (who owes, how much, how old), so that I can chase outstanding money.
26. As a user, I want an Expense report by category, so that I can see where money goes.
27. As a user, I want a "Paid students for a month" report, so that I can see who has and hasn't paid for a given month.
28. As a user, I want a summarized finance report, so that I can present an overview to school leadership.
29. As a user, I want to export students for a Class (or All classes), so that I can share registers.
30. As a user, I want every report to have a CSV export, so that numbers can be analyzed in a spreadsheet.
31. As an Admin, I want to browse the audit log, so that every action is attributable and disputes can be settled.
32. As a user, I want the app to back up automatically on startup and via a manual button, so that records are never lost.
33. As a user, I want the app to open automatically in the browser when launched, so that I don't need to remember a URL.
34. As a user, I want the app to quit from a system-tray icon, so that the hidden server can be stopped cleanly.
35. As a user, I want the app to refuse to run twice, so that two servers never fight over the database.
36. As an Admin, I want to manage users (create/disable), so that staff changes are reflected in access.
37. As an Admin, I want to shut the app down from within the UI, so that the office can stop it without the tray.

## Implementation Decisions

- **Stack:** FastAPI + SQLite + Jinja2 + HTMX + Tailwind (bundled, offline) + Chart.js. Packaged with PyInstaller as a hidden (no-console) single .exe with a pystray tray icon. Server runs on localhost; the default browser opens automatically; a socket/lock-file guard enforces a single instance.
- **Architecture — modular folders:** feature packages (`auth`, `classes`, `students`, `fees`, `payments`, `expenses`, `arrears`, `reports`, `admin`, `system`) each containing routes + service + templates/partials; a shared layer underneath (db, config, base layout). UI is composed of reusable Jinja2 partials/macros.
- **The seam:** all business logic lives in a **service layer**; routes are thin adapters. Tests target the services only (see Testing Decisions). This is the single testing seam.
- **Money:** stored as integer cents. No floats.
- **Data access:** SQLAlchemy ORM over SQLite; schema created via `create_all` on startup (migrations out of scope for v1). Tests use an in-memory SQLite database.
- **Auth:** server-side sessions (signed cookie), passwords hashed (PBKDF2). Roles: `admin`, `finance`. A `users` table plus an `is_admin`/role column or role field. Setup wizard on first run (empty user table → setup screen).
- **Domain model:** `User`, `Class` (status: active/completed/inactive), `FeeItem` (class-scoped structure), `Student` (status: active/inactive), `Charge` (one per student per month, sum of applied items at generation time; snapshot the item breakdown so later structure edits don't rewrite history), `Adjustment` (extras/waivers on a charge), `Payment` (amount, method, date, recorded_by), `Credit` (overpayment), `Expense` (category, amount, date, description, method), `ExpenseCategory`, `AuditLogEntry`, `GenerationRecord` (class+month+year → already generated).
- **Fee generation:** form = Class (or All) + Month + Year + Generate. `GenerationRecord` keyed on (class_id, month, year) makes it duplicate-safe. Charge per student = sum of fee items at generation time. Charges created inside one transaction; audit entry per generation.
- **Payment allocation:** a payment is applied to the oldest unpaid charges first (per student), partial application supported; if the payment exceeds remaining charges, the excess becomes a `Credit`. All within one transaction. Receipt = printable HTML page rendered from the payment record.
- **Arrears:** computed as sum of unpaid charge balances minus credits; report shows per-student owed amount and age (oldest unpaid charge date). Inactive students and completed classes keep their arrears.
- **Reports:** dashboard aggregates (charts via Chart.js); reports rendered as HTML tables with an Export CSV button (StreamingResponse + csv module). No PDF engine.
- **Audit log:** append-only table; every payment, expense, charge generation, adjustment, user/class/structure change logged with user, timestamp, and summary of change. Admin-only browse.
- **Backup:** on startup copy the SQLite file to `backups/` (keep ~30, rotating); manual "Backup now" button; restore is manual (copy a backup file back) in v1.
- **Deletion policy:** no hard deletes; archive (status flags). All destructive-looking actions are status transitions.

## UI Design (from the UI grilling session, UI-1..UI-15)

- **Look & feel:** clean modern dashboard — light theme, sidebar + topbar, cards, subtle shadows, generous spacing.
- **Navigation:** grouped sidebar + topbar. Groups: **School** (Classes, Students), **Finance** (Fees, Payments, Expenses), **Reports**, **System** (Audit, Settings). Sidebar collapsible.
- **Colors:** teal/emerald primary. Semantic: green = money in/paid, red = arrears/expenses/overdue, amber = partial/warnings, slate = neutral. Badges/chips carry meaning — color is never the only signal.
- **Component library:** **daisyUI + Tailwind**, every control wrapped as a reusable Jinja2 partial/macro. Bundled offline.
- **Feedback & interactions:** toasts (success/error/warning, auto-dismiss), confirm dialogs for irreversible actions, inline loading states, friendly empty states.
- **Typography & icons:** **Inter bundled** locally (woff2, system fallback) + **Heroicons inline SVG** macros.
- **Key screens:** fee generation = single card (Class/All + Month + Year + Generate) with a confirm dialog showing per-class breakdown; record payment = search student with live balance → amount/method → confirmation line → save → toast + print receipt; student account = header with big color-coded balance, expandable charges with item breakdown + adjustments, payments list, balance footer, actions; class page = header (name/status/fee summary), action bar, students table with paid/unpaid/all filter; reports = one reusable template (filter bar, summary line, table, Export CSV), arrears age color-coded.
- **Print:** print CSS hides app chrome; print-ready receipt and statement templates.
- **Login & setup:** minimal centered login card (show/hide password, error banner) + 3-step setup wizard (Welcome → Admin account → All set). Only pages without the sidebar.
- **Devices & accessibility:** desktop-first, adapts down to ~1024px (sidebar collapses). Mobile out of scope. Keyboard-navigable, visible focus rings.

## Testing Decisions

- **What makes a good test:** a test exercises external behavior of the service layer — given inputs, assert the resulting state and effects (charges created, balances computed, duplicates refused, audit rows written). No test reaches into implementation details of a service.
- **Single seam:** all business-rule tests run against the service layer with an in-memory SQLite database. Route/template layers are verified manually in the browser (HTMX + templates are presentation).
- **Modules under test:** fee generation (incl. duplicate-safety), payment allocation (oldest-first, partials, credits), arrears computation, adjustments, expenses + categories, report aggregations, audit logging, backup rotation logic.
- **Prior art:** none yet — greenfield. The first service test establishes the pattern (pytest + in-memory DB fixture) that all later tests follow.

## Out of Scope

- Budgeting, donations, grants, payroll
- PDF generation (printable HTML only)
- Expense attachments / uploaded receipts
- Refunds (credit system covers overpayment)
- Family/guardian-level billing (students billed individually)
- Automated fee generation (manual button by design)
- Payment gateways / mobile money integrations
- Multi-school / multi-branch support
- Network/multi-machine deployment
- Schema migrations tooling (create_all for v1)
- User-facing multi-language (English only), USD only

## Further Notes

- Driven by the grilling session recorded in `project-decisions.md` (single source of truth for decisions).
- Currency: USD. UI language: English. Runs on one office PC, offline-capable (assets bundled).
- The .exe hides the console; the app is operated through the browser; quitting happens via the tray icon or the in-app shutdown (Admin).
