# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A single school's admin/secretary, working at one desk — either the office PC (packaged Windows .exe) or a locally served web app. Their daily job: keep the school's money flows in order — record payments and expenses, and chase arrears against each month's expected fee. A Finance officer role records payments/expenses and applies waivers; the Admin owns structure, users, and settings. Same desk, same daily rhythm.

## Product Purpose

Run one real school's finances end-to-end: fee templates with class defaults, expected-vs-paid billing derived from enrollment, per-student waivers, payment recording with printable receipts, expense recording, arrears tracking, reports with CSV export, and a complete audit trail. Success means the school's month-end numbers are correct, complete, and explainable.

## Positioning

A self-contained, single-machine finance app for one real school. No accounts, no cloud dependency, no setup beyond first launch. Billing is derived from enrollment — expected vs paid per month — and every meaningful action is audited, so the books are defensible and the workflow is simple.

## Operating Context

- One desk, one machine; app served on localhost (packaged Windows .exe with tray icon) or via Docker at ict.hgeesey.store.
- Two roles log in with staff accounts; server-side sessions; PBKDF2 password hashing.
- Manual monthly billing rhythm: a student is expected to pay each month they are enrolled; payments are recorded against a specific month.
- Printed receipts and student statements carry the school's own name, logo, and contact block, rendered at print time from the current profile.

## Capabilities and Constraints

- Classes (Active / Completed / Inactive) with a default fee template; students added manually or imported via CSV; archive instead of delete.
- Fee billing is derived from enrollment: each owed month's expected amount is the template amount in force minus waivers, compared against payments tagged to that month — no charge rows, no generation step.
- Per-(student, month) waivers (Admin-only); waivers reduce a month's expected amount but never below zero.
- Payments: partial payments clear oldest unpaid months first; overpayment becomes credit; printable receipt per payment.
- Expenses against Admin-managed categories, with cash/bank/other method.
- Reports with CSV export; arrears by age; dashboard charts.
- Full audit log; automatic backup on startup plus manual "Backup now", keeping ~30 copies.
- USD, English. Money stored in integer cents. SQLite single file, env-driven data directory.
- Two roles only: Admin and Finance officer.

## Brand Commitments

- The software is called "School Finance"; the school's own name, logo, and contact details appear in the app shell and on printed documents.
- Visual: must stay light and professional (confirmed 2026-08-09). No other binding brand constraints.

## Evidence on Hand

- CONTEXT.md glossary (School Name vs App Name), README feature list, project-decisions.md decision log, `.scratch/school-finance/spec.md` and 18 implemented tickets.
- Live deployment at ict.hgeesey.store (outcome recorded in project-decisions.md, 2026-08-07).

## Product Principles

- **Money truth is sacred:** history is immutable (derived from enrollment, so it is always reconstructible), every mutation is audited, and numbers must never be misread.
- **One desk, one person:** the daily flow (expected → collect → record → chase) takes the fewest clicks and zero head-scratching.
- **Restraint earns trust:** a calm, light, professional surface where structure and the numbers themselves carry the weight.
- **Roles keep the school safe:** structure and system mutations are Admin-gated; Finance moves money day-to-day.
